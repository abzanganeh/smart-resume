"""Billing router — credits, subscriptions, refund-request, Stripe webhook.

Implements every route from IMPLEMENTATION_PLAN.md §6 "Credits,
Subscriptions, Stripe" table.  Slowapi rate limits match that table
exactly (e.g. ``120/min`` on read endpoints, ``30/min`` on mutations,
``10/min`` on pause/unpause/refund).

The webhook route ``POST /api/webhooks/stripe`` is the security-critical
surface and follows the §7.4 receive-flow:

1. Verify signature with ``STRIPE_WEBHOOK_SECRET`` *before any DB write*;
   reject with HTTP 400 on mismatch.
2. ``INSERT … ON CONFLICT (event_id) DO NOTHING`` — duplicate delivery
   returns HTTP 200 immediately.
3. Set ``status=processing``; dispatch to the right handler in
   :mod:`app.services.billing.webhook_handler`; set ``status=processed``.
4. On exception: mark ``status=failed``, persist ``last_error``, return
   HTTP 500 so Stripe retries.
5. After ``STRIPE_WEBHOOK_MAX_ATTEMPTS`` (default 5): mark
   ``status=needs_review``, return HTTP 200 to stop retries, log a
   placeholder for Step 35's :class:`AdminAuditLog` row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.models.billing import (
    AdminAuditLog,
    CreditKind,
    LLMUpgradeTier,
    RefundInitiator,
    RefundReason,
    RefundRecord,
    StripeWebhookEvent,
    StripeWebhookStatus,
    Subscription,
    SubscriptionStatus,
)
from app.models.user import CreditTransaction, User
from app.services.auth.dependencies import get_current_user
from app.services.billing import refund as refund_service
from app.services.billing import subscription as sub_service
from app.services.billing import webhook_handler
from app.services.billing.credits import get_balance
from app.services.billing.credit_spend import (
    credits_locked_detail,
    credits_locked_until_verification,
    spendable_free_credits,
)
from app.services.billing.exhaustion_top_up import (
    get_exhaustion_top_up_eligibility,
    grant_exhaustion_top_up,
)
from app.services.billing.exceptions import (
    BillingCycleMismatchError,
    BillingError,
    CreditsLockedUntilVerificationError,
    InsufficientCreditsError,
    PriceUnresolvedError,
    RefundError,
    SubscriptionPauseNotAllowedError,
    WebhookSignatureError,
)
from app.services.billing.flint_credits import (
    FLINT_PRODUCT,
    create_hold,
    deduct_flint_credits,
    release_hold,
)
from app.services.billing.llm_upgrade import (
    VALID_LLM_UPGRADE_CODES,
    TierStatus,
    get_phase3_tier_status,
    normalize_llm_upgrade_code,
)
from app.services.billing.plan_code import resolve_plan_code_for_subscription
from app.services.billing.price_resolver import reverse_lookup_code
from app.services.billing.public_prices import display_name_for_plan_code
from app.services.billing.tier_limits_lookup import (
    get_active_tier_limits,
    registration_grant_credits,
)

log = structlog.get_logger("billing.router")

router = APIRouter(tags=["billing"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class BalanceResponse(BaseModel):
    free: int
    better: int
    best: int
    legacy_credit_balance: int


class FreeTierResponse(BaseModel):
    starting_credits: int


class CreditTransactionItem(BaseModel):
    id: uuid.UUID
    delta: int
    credit_kind: Literal["free", "better", "best"]
    reason: str
    action: str
    note: str | None = None
    session_id: str | None = None
    related_subscription_id: uuid.UUID | None = None
    related_resume_record_id: uuid.UUID | None = None
    stripe_event_id: str | None = None
    created_at: datetime


class CreditTransactionPage(BaseModel):
    items: list[CreditTransactionItem]
    total: int


class FlintDeductRequest(BaseModel):
    action: str = Field(..., min_length=1, max_length=64)
    product: str = Field(default=FLINT_PRODUCT, min_length=1, max_length=64)
    session_id: str = Field(..., min_length=1, max_length=64)


class FlintDeductResponse(BaseModel):
    balance: int
    transaction_id: str


class FlintHoldRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    amount: int = Field(..., gt=0, le=10_000)


class FlintHoldResponse(BaseModel):
    hold_id: str


class FlintReleaseHoldRequest(BaseModel):
    hold_id: str = Field(..., min_length=36, max_length=36)


class CheckoutRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    success_url: str = Field(..., max_length=2048)
    cancel_url: str = Field(..., max_length=2048)


class CheckoutResponse(BaseModel):
    url: str
    id: str


class PortalRequest(BaseModel):
    return_url: str = Field(..., max_length=2048)


class PortalResponse(BaseModel):
    url: str


class ChangePlanRequest(BaseModel):
    new_code: str = Field(..., min_length=1, max_length=64)


class PauseRequest(BaseModel):
    """Pause window — accepts either ``pause_until`` (preferred) or ``days``.

    ``pause_until`` is the canonical contract per Step 37 / §19.8: it
    encodes a deterministic resume point and lets the frontend show
    "paused until 12 Aug" without recomputing from a relative day count.
    The ``days`` shape is kept for backward compatibility with the
    Step 7 dashboard implementation.
    """

    pause_until: datetime | None = Field(
        default=None,
        description="UTC timestamp when Stripe should resume billing.",
    )
    days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description=(
            "Days from now until resume.  Service enforces 7..90; longer "
            "windows are rejected with HTTP 400 invalid_pause_window."
        ),
    )


class SubscriptionView(BaseModel):
    id: uuid.UUID
    plan: str
    billing_cycle: str
    # Canonical tier code and marketing label; ``plan`` alone cannot distinguish
    # Pro / Pro+ / Premium because the legacy enum only stores the interval.
    plan_code: str
    plan_display_name: str
    llm_upgrade: str
    llm_upgrade_billing_cycle: str | None
    status: str
    trial_ends_at: datetime | None
    period_start: datetime
    period_end: datetime
    resumes_used: int
    resumes_limit: int
    searches_used: int
    searches_limit: int
    fit_analyses_limit: int
    whisper_uses_used: int
    whisper_uses_limit: int | None
    upgraded_resumes_used: int
    cancel_at_period_end: bool
    payment_failed_at: datetime | None
    paused_at: datetime | None
    pause_resumes_at: datetime | None


class SubscriptionCurrentResponse(BaseModel):
    subscription: SubscriptionView | None
    credit_balance: int
    spendable_credit_balance: int
    credits_locked_until_verification: bool
    exhaustion_top_up_eligible: bool = False
    exhaustion_top_up_amount: int = 0
    free_tier_usage_note: str = (
        "Credits pay for resume tailoring, cover letters, and similar AI actions. "
        "Job search, checkups, fit analysis, story sessions, and tracker rows use "
        "separate monthly counters on the free plan."
    )


class RefundRequestPayload(BaseModel):
    reason: Literal[
        "self_service_24h",
        "self_service_unused",
        "manual",
        "chargeback",
    ] = "manual"
    note: str = Field("", max_length=2000)
    within_24h: bool = Field(
        default=False,
        description=(
            "When true, treat as self-service 24h refund (§18.3 row 1) "
            "and call Stripe directly without admin queueing.  Service "
            "validates the timestamp against the most recent "
            "subscription's created_at."
        ),
    )
    amount_usd: float | None = Field(default=None, ge=0)
    payment_intent: str | None = Field(default=None, max_length=255)
    charge: str | None = Field(default=None, max_length=255)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _subscription_credit_fields(
    user: User, *, free_credits: int, exhaustion_top_up_eligible: bool = False
) -> dict[str, int | bool | str]:
    return {
        "credit_balance": free_credits,
        "spendable_credit_balance": spendable_free_credits(user, balance=free_credits),
        "credits_locked_until_verification": credits_locked_until_verification(
            user, balance=free_credits
        ),
        "exhaustion_top_up_eligible": exhaustion_top_up_eligible,
        "exhaustion_top_up_amount": settings.EXHAUSTION_TOP_UP_CREDITS,
    }


def _billing_error_to_http(exc: BillingError) -> HTTPException:
    if isinstance(exc, PriceUnresolvedError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "price_unresolved", "stripe_code": exc.code},
        )
    if isinstance(exc, BillingCycleMismatchError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "billing_cycle_mismatch"},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "billing_error", "message": str(exc)},
    )


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


@router.get("/api/billing/free-tier", response_model=FreeTierResponse)
@limiter.limit("120/minute")
async def billing_free_tier(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FreeTierResponse:
    amount = await registration_grant_credits(db)
    return FreeTierResponse(starting_credits=amount)


@router.get("/api/credits/balance")
@limiter.limit("120/minute")
async def credits_balance(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> BalanceResponse:
    free = await get_balance(db, user_id=user.id, credit_kind=CreditKind.free)
    better = await get_balance(db, user_id=user.id, credit_kind=CreditKind.better)
    best = await get_balance(db, user_id=user.id, credit_kind=CreditKind.best)
    return BalanceResponse(
        free=free,
        better=better,
        best=best,
        legacy_credit_balance=user.credit_balance,
    )


@router.post("/api/credits/exhaustion-top-up")
@limiter.limit("5/minute")
async def claim_exhaustion_top_up(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, int | bool]:
    eligibility = await get_exhaustion_top_up_eligibility(session=db, user=user)
    if not eligibility.eligible:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "exhaustion_top_up_unavailable",
                "reason": eligibility.reason or "not_eligible",
            },
        )
    try:
        granted = await grant_exhaustion_top_up(db, user=user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "exhaustion_top_up_unavailable", "reason": str(exc)},
        ) from exc
    return {"ok": True, "granted": granted}


@router.get("/api/credits/transactions")
@limiter.limit("120/minute")
async def credits_transactions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 50,
    offset: int = 0,
) -> CreditTransactionPage:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = (
        await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user.id)
            .order_by(desc(CreditTransaction.created_at))
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        CreditTransactionItem(
            id=r.id,
            delta=r.delta,
            credit_kind=r.credit_kind.value,
            reason=r.reason or r.action.value,
            action=r.action.value,
            note=r.note,
            session_id=r.session_id,
            related_subscription_id=r.related_subscription_id,
            related_resume_record_id=r.related_resume_record_id,
            stripe_event_id=r.stripe_event_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return CreditTransactionPage(items=items, total=len(items))


@router.post("/api/credits/deduct")
@limiter.limit("30/minute")
async def credits_deduct(
    request: Request,
    payload: FlintDeductRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FlintDeductResponse:
    """Flint metered debit — Strategy B Phase 3 scaffold."""
    try:
        balance, tx_id = await deduct_flint_credits(
            db,
            user_id=user.id,
            action=payload.action,
            product=payload.product,
            session_id=payload.session_id,
        )
    except CreditsLockedUntilVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=credits_locked_detail(balance=exc.balance),
        ) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "insufficient_credits",
                "credit_kind": exc.credit_kind,
                "balance": exc.balance,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_credit_action", "message": str(exc)},
        ) from exc
    await db.commit()
    return FlintDeductResponse(balance=balance, transaction_id=str(tx_id))


@router.post("/api/credits/hold")
@limiter.limit("30/minute")
async def credits_hold(
    request: Request,
    payload: FlintHoldRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FlintHoldResponse:
    """Reserve credits for a live session — in-process stub until Postgres holds."""
    hold_id = create_hold(
        user_id=user.id,
        session_id=payload.session_id,
        amount=payload.amount,
    )
    return FlintHoldResponse(hold_id=str(hold_id))


@router.post("/api/credits/release-hold")
@limiter.limit("30/minute")
async def credits_release_hold(
    request: Request,
    payload: FlintReleaseHoldRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    try:
        hold_uuid = uuid.UUID(payload.hold_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_hold_id"},
        ) from exc
    try:
        release_hold(hold_id=hold_uuid, user_id=user.id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "hold_not_found"},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "hold_forbidden"},
        ) from exc
    return {"ok": True}


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


@router.post("/api/subscriptions/checkout")
@limiter.limit("30/minute")
async def subscriptions_checkout(
    request: Request,
    payload: CheckoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CheckoutResponse:
    try:
        result = await sub_service.create_checkout_session(
            db,
            user=user,
            code=payload.code,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except BillingError as exc:
        raise _billing_error_to_http(exc) from exc
    return CheckoutResponse(
        url=str(result.get("url", "")),
        id=str(result.get("id", "")),
    )


@router.post("/api/subscriptions/portal")
@limiter.limit("30/minute")
async def subscriptions_portal(
    request: Request,
    payload: PortalRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PortalResponse:
    try:
        result = await sub_service.create_portal_session(
            db, user=user, return_url=payload.return_url
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        ) from exc
    return PortalResponse(url=str(result.get("url", "")))


@router.post("/api/subscriptions/cancel")
@limiter.limit("30/minute")
async def subscriptions_cancel(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        await sub_service.cancel_at_period_end(db, user=user)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        )
    return {"ok": True, "pending_via_webhook": True}


@router.post("/api/subscriptions/resume")
@limiter.limit("30/minute")
async def subscriptions_resume(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        await sub_service.resume_subscription(db, user=user)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        )
    return {"ok": True, "pending_via_webhook": True}


@router.post("/api/subscriptions/change-plan")
@limiter.limit("30/minute")
async def subscriptions_change_plan(
    request: Request,
    payload: ChangePlanRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        await sub_service.change_plan(db, user=user, new_code=payload.new_code)
    except BillingError as exc:
        raise _billing_error_to_http(exc) from exc
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        )
    return {"ok": True, "pending_via_webhook": True}


@router.post("/api/subscriptions/pause")
@limiter.limit("10/minute")
async def subscriptions_pause(
    request: Request,
    payload: PauseRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Pause a subscription per §7.7 + §19.8.

    Cycle constraint: only Monthly + Yearly base plans are eligible;
    Daily / Weekly plans receive HTTP 422 ``pause_not_allowed``.
    Window constraint: between ``SUBSCRIPTION_PAUSE_MIN_DAYS`` (7) and
    ``SUBSCRIPTION_PAUSE_MAX_DAYS`` (90); out-of-range receives HTTP
    400 ``invalid_pause_window``.

    Persistent state changes happen only via the
    ``customer.subscription.updated`` webhook (§7.6 row 5).
    """
    if payload.pause_until is None and payload.days is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "pause_until_or_days_required"},
        )
    try:
        await sub_service.pause_subscription(
            db,
            user=user,
            pause_until=payload.pause_until,
            days=payload.days,
        )
    except SubscriptionPauseNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "pause_not_allowed",
                "plan": exc.plan,
                "billing_cycle": exc.billing_cycle,
            },
        ) from exc
    except ValueError as exc:
        msg = str(exc)
        if "between" in msg or "must be provided" in msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_pause_window",
                    "min_days": settings.SUBSCRIPTION_PAUSE_MIN_DAYS,
                    "max_days": settings.SUBSCRIPTION_PAUSE_MAX_DAYS,
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        ) from exc
    return {"ok": True, "pending_via_webhook": True}


@router.post("/api/subscriptions/unpause")
@limiter.limit("10/minute")
async def subscriptions_unpause(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        await sub_service.unpause_subscription(db, user=user)
    except ValueError as exc:
        if "cannot unpause from status" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_unpause_state"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        ) from exc
    return {"ok": True, "pending_via_webhook": True}


@router.get("/api/subscriptions/current")
@limiter.limit("120/minute")
async def subscriptions_current(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionCurrentResponse:
    free_credits = await get_balance(db, user_id=user.id, credit_kind=CreditKind.free)
    if user.credit_balance != free_credits:
        user.credit_balance = max(0, free_credits)
        await db.flush()

    sub = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(Subscription.status != SubscriptionStatus.expired)
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if sub is None:
        top_up = await get_exhaustion_top_up_eligibility(session=db, user=user)
        return SubscriptionCurrentResponse(
            subscription=None,
            **_subscription_credit_fields(
                user,
                free_credits=free_credits,
                exhaustion_top_up_eligible=top_up.eligible,
            ),
        )

    plan_code = resolve_plan_code_for_subscription(
        sub, plan_config_code=await reverse_lookup_code(db, sub.stripe_price_id)
    )
    limits = await get_active_tier_limits(db, plan_code)

    return SubscriptionCurrentResponse(
        subscription=SubscriptionView(
            id=sub.id,
            plan=sub.plan.value,
            billing_cycle=sub.billing_cycle.value,
            plan_code=plan_code,
            plan_display_name=display_name_for_plan_code(plan_code),
            resumes_limit=limits.resumes_per_period,
            searches_limit=limits.searches_per_period,
            fit_analyses_limit=limits.fit_analyses_per_period,
            whisper_uses_used=sub.whisper_uses_used,
            whisper_uses_limit=limits.whisper_uses_per_period,
            llm_upgrade=sub.llm_upgrade.value,
            llm_upgrade_billing_cycle=(
                sub.llm_upgrade_billing_cycle.value
                if sub.llm_upgrade_billing_cycle is not None
                else None
            ),
            status=sub.status.value,
            trial_ends_at=sub.trial_ends_at,
            period_start=sub.period_start,
            period_end=sub.period_end,
            resumes_used=sub.resumes_used,
            searches_used=sub.searches_used,
            upgraded_resumes_used=sub.upgraded_resumes_used,
            cancel_at_period_end=sub.cancel_at_period_end,
            payment_failed_at=sub.payment_failed_at,
            paused_at=sub.paused_at,
            pause_resumes_at=sub.pause_resumes_at,
        ),
        **_subscription_credit_fields(user, free_credits=free_credits),
    )


class LLMUpgradeCheckoutRequest(BaseModel):
    """Spec-canonical add-on codes per IMPLEMENTATION_PLAN §7.1.

    ``better_5pack`` is the canonical name for what the legacy webhook
    handler / price resolver call ``better_pack`` — both are accepted
    here and collapsed to the internal name in
    :func:`normalize_llm_upgrade_code`.
    """

    code: Literal[
        "better_5pack",
        "better_monthly",
        "better_yearly",
        "best_per_resume",
        "best_monthly",
        "best_yearly",
    ]
    success_url: str = Field(..., max_length=2048)
    cancel_url: str = Field(..., max_length=2048)


class LLMUpgradeStatusResponse(BaseModel):
    entitled_tier: Literal["standard", "better", "best"]
    better_subscription_active: bool
    best_subscription_active: bool
    better_credits_balance: int
    upgraded_resumes_used: int
    upgraded_resumes_limit: int
    best_soft_cap_hit: bool
    base_billing_cycle: Literal["recurring", "yearly"] | None


@router.post("/api/subscriptions/llm-upgrade/checkout")
@limiter.limit("30/minute")
async def subscriptions_llm_upgrade_checkout(
    request: Request,
    payload: LLMUpgradeCheckoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CheckoutResponse:
    """LLM add-on checkout removed — quality is included in subscription tier."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "llm_upgrade_removed",
            "message": "LLM quality is included in your subscription tier. Upgrade your plan on Billing.",
        },
    )


@router.get("/api/subscriptions/llm-upgrade/status")
@limiter.limit("120/minute")
async def subscriptions_llm_upgrade_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> LLMUpgradeStatusResponse:
    """Snapshot of the user's Phase 3 LLM tier entitlements (Step 19).

    The frontend selector on the rewrite page calls this to render the
    Better-credit badge, the Best soft-cap banner, and to gate the
    yearly add-on option behind a yearly base subscription.
    """
    status_view: TierStatus = await get_phase3_tier_status(db, user_id=user.id)
    cycle = status_view.base_billing_cycle
    if cycle not in (None, "recurring", "yearly"):
        cycle = None
    return LLMUpgradeStatusResponse(
        entitled_tier=status_view.entitled_tier,
        better_subscription_active=status_view.better_subscription_active,
        best_subscription_active=status_view.best_subscription_active,
        better_credits_balance=status_view.better_credits_balance,
        upgraded_resumes_used=status_view.upgraded_resumes_used,
        upgraded_resumes_limit=status_view.upgraded_resumes_limit,
        best_soft_cap_hit=status_view.best_soft_cap_hit,
        base_billing_cycle=cycle,  # type: ignore[arg-type]
    )


@router.post("/api/subscriptions/refund-request")
@limiter.limit("10/minute")
async def subscriptions_refund_request(
    request: Request,
    payload: RefundRequestPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Refund request entry point — auto-approves the 24h self-service path.

    Per §18.3:

    - ``within_24h=True`` → call :func:`refund_service.self_service_refund`
      which validates the window, calls Stripe directly, persists the
      :class:`RefundRecord`, and writes an :class:`AdminAuditLog` row.
    - Anything else → queue a pending :class:`RefundRecord` for
      super-admin review (Step 35).  Stripe is **not** contacted on
      this branch; the admin approval flow issues the actual
      ``stripe.Refund.create`` call.
    """
    if payload.within_24h or payload.reason == "self_service_24h":
        try:
            decision = await refund_service.self_service_refund(
                db,
                user=user,
                amount_usd=payload.amount_usd,
                reason_note=payload.note or "self-service 24h",
                payment_intent=payload.payment_intent,
                charge=payload.charge,
                request_ip=request.client.host if request.client else "",
                request_user_agent=request.headers.get("user-agent", ""),
            )
        except RefundError as exc:
            if exc.stage == "window":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "refund_window_expired"},
                ) from exc
            if exc.stage == "lookup":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "no_subscription"},
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "refund_failed",
                    "stage": exc.stage,
                    "message": exc.message,
                },
            ) from exc
        log.info(
            "billing.refund_self_service_completed",
            user_id=str(user.id),
            record_id=str(decision.record_id),
            stripe_refund_id=decision.stripe_refund_id,
        )
        return {
            "ok": True,
            "auto_approved": True,
            "id": str(decision.record_id),
            "stripe_refund_id": decision.stripe_refund_id,
        }

    sub = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    record = RefundRecord(
        id=uuid.uuid4(),
        user_id=user.id,
        subscription_id=sub.id if sub is not None else None,
        # Pending-request placeholder; the real Stripe refund id is
        # filled in by the admin approval flow.  Preserve uniqueness
        # via the row id.
        stripe_refund_id=f"pending_{uuid.uuid4().hex}",
        amount_usd=payload.amount_usd if payload.amount_usd is not None else 0,
        reason=RefundReason(payload.reason),
        initiated_by=RefundInitiator.user,
    )
    db.add(record)
    await db.flush()
    log.info(
        "billing.refund_request_queued",
        user_id=str(user.id),
        record_id=str(record.id),
        reason=payload.reason,
    )
    return {"ok": True, "id": str(record.id)}


# ---------------------------------------------------------------------------
# Stripe webhook receiver  (§7.4)
# ---------------------------------------------------------------------------


@router.post("/api/webhooks/stripe", include_in_schema=False)
@limiter.exempt
async def stripe_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    if not settings.STRIPE_WEBHOOK_SECRET:
        log.error("billing.webhook.missing_secret")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "missing_webhook_secret"},
        )
    try:
        event = stripe.Webhook.construct_event(
            payload=raw_body,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        log.warning("billing.webhook.signature_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_signature"},
        ) from exc
    except Exception as exc:  # noqa: BLE001 — defensive guard
        # Never reach DB on any pre-verify failure.
        log.warning("billing.webhook.parse_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_payload"},
        ) from exc

    event_dict = _stripe_event_to_dict(event)
    return await _persist_and_dispatch(db, event_dict)


async def _persist_and_dispatch(
    db: AsyncSession, event: dict[str, Any]
) -> dict[str, Any]:
    """Idempotency + ordering wrapper around handler dispatch.

    Splits the job into two micro-transactions because the webhook row
    must survive even if the handler raises (so the next retry can see
    ``attempts``).  Pseudocode:

    ```
    INSERT … ON CONFLICT (event_id) DO NOTHING -> commit
    SELECT row by event_id
    if processed → return 200 (duplicate)
    if attempts >= MAX → mark needs_review, log, return 200
    set status=processing, attempts++ -> commit
    try: dispatch(handler) -> set status=processed, processed_at=now -> commit
    except: set status=failed, last_error -> commit -> raise 500
    ```
    """
    event_id = event["id"]
    event_type = event["type"]
    obj = event.get("data", {}).get("object", {}) or {}
    related_subscription_id = (
        obj.get("id")
        if event_type.startswith("customer.subscription.")
        else obj.get("subscription")
    )
    related_customer_id = obj.get("customer")
    created_event_at = datetime.fromtimestamp(
        int(event.get("created", 0) or 0), tz=timezone.utc
    )

    # Step 1 — INSERT … ON CONFLICT DO NOTHING.
    insert_stmt = (
        pg_insert(StripeWebhookEvent)
        .values(
            id=uuid.uuid4(),
            event_id=event_id,
            event_type=event_type,
            livemode=bool(event.get("livemode", False)),
            received_at=datetime.now(timezone.utc),
            status=StripeWebhookStatus.received,
            attempts=0,
            payload=event,
            related_subscription_id=str(related_subscription_id)
            if related_subscription_id
            else None,
            related_customer_id=str(related_customer_id)
            if related_customer_id
            else None,
            created_event_at=created_event_at,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(StripeWebhookEvent.id)
    )
    inserted_id = (await db.execute(insert_stmt)).scalar_one_or_none()
    await db.commit()
    row = (
        await db.execute(
            select(StripeWebhookEvent).where(StripeWebhookEvent.event_id == event_id)
        )
    ).scalar_one()
    if inserted_id is None and row.status in {
        StripeWebhookStatus.processed,
        StripeWebhookStatus.needs_review,
    }:
        # Already terminally handled: duplicate webhook delivery becomes
        # a no-op and returns 200 immediately.
        log.info("billing.webhook.duplicate_ack", event_id=event_id, status=row.status.value)
        return {"received": True, "duplicate": True}

    if row.attempts >= settings.STRIPE_WEBHOOK_MAX_ATTEMPTS:
        row.status = StripeWebhookStatus.needs_review
        await db.commit()
        await _write_admin_audit(
            db,
            action="stripe_event_needs_review",
            target_kind="stripe_webhook_event",
            target_id=row.event_id,
            after_json={
                "event_type": row.event_type,
                "attempts": row.attempts,
                "last_error": row.last_error or "",
            },
        )
        log.error(
            "billing.webhook.needs_review_after_max_attempts",
            event_id=event_id,
            event_type=event_type,
            attempts=row.attempts,
        )
        # AdminAuditLog row will land in Step 35; for now ack with 200
        # so Stripe stops retrying.
        return {"received": True, "needs_review": True}

    row.status = StripeWebhookStatus.processing
    row.attempts = (row.attempts or 0) + 1
    await db.commit()

    # Step 3 — dispatch.
    try:
        await webhook_handler.dispatch(db, event)
    except Exception as exc:  # noqa: BLE001 — webhook resilience
        await db.rollback()
        # After max attempts (default: 5), park in needs_review and stop
        # retries (return 200) while writing an admin audit row.
        if row.attempts >= settings.STRIPE_WEBHOOK_MAX_ATTEMPTS:
            await _mark_needs_review(db, row, str(exc))
            await _write_admin_audit(
                db,
                action="stripe_event_needs_review",
                target_kind="stripe_webhook_event",
                target_id=row.event_id,
                after_json={
                    "event_type": row.event_type,
                    "attempts": row.attempts,
                    "last_error": (str(exc) or "")[:2000],
                },
            )
            return {"received": True, "needs_review": True}
        await _mark_failed(db, row, str(exc))
        log.error(
            "billing.webhook.handler_failed",
            event_id=event_id,
            event_type=event_type,
            attempts=row.attempts,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "handler_failed"},
        ) from exc

    row.status = StripeWebhookStatus.processed
    row.processed_at = datetime.now(timezone.utc)
    row.last_error = None
    await db.commit()
    log.info(
        "billing.webhook.processed",
        event_id=event_id,
        event_type=event_type,
        attempts=row.attempts,
    )
    return {"received": True}


async def _mark_failed(
    db: AsyncSession, row: StripeWebhookEvent, message: str
) -> None:
    # Re-fetch the row in a fresh transaction so the rollback above
    # doesn't undo the status flip.
    fresh = (
        await db.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.id == row.id
            )
        )
    ).scalar_one_or_none()
    if fresh is None:
        return
    fresh.status = StripeWebhookStatus.failed
    fresh.last_error = (message or "")[:2000]
    await db.commit()


async def _mark_needs_review(
    db: AsyncSession, row: StripeWebhookEvent, message: str
) -> None:
    fresh = (
        await db.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.id == row.id
            )
        )
    ).scalar_one_or_none()
    if fresh is None:
        return
    fresh.status = StripeWebhookStatus.needs_review
    fresh.last_error = (message or "")[:2000]
    await db.commit()


async def _write_admin_audit(
    db: AsyncSession,
    *,
    action: str,
    target_kind: str,
    target_id: str,
    after_json: dict[str, Any],
) -> None:
    row = AdminAuditLog(
        id=uuid.uuid4(),
        actor_admin_id=None,
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        before_json={},
        after_json=after_json,
        ip="system:webhook",
        user_agent="stripe-webhook",
        request_id="",
    )
    db.add(row)
    await db.commit()


def _stripe_event_to_dict(event: Any) -> dict[str, Any]:
    """Convert a verified ``stripe.Event`` into a plain dict.

    The SDK exposes both attribute-style and dict-style access; we
    normalize to dict so downstream handlers don't depend on the SDK
    surface.
    """
    if isinstance(event, dict):
        return event
    if hasattr(event, "to_dict_recursive"):
        return event.to_dict_recursive()
    if hasattr(event, "to_dict"):
        return event.to_dict()
    raise WebhookSignatureError("could not normalize verified event payload")


__all__ = ["router"]
