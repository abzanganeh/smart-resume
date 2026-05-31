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
    CreditKind,
    PlanConfig,
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
from app.services.billing import subscription as sub_service
from app.services.billing import webhook_handler
from app.services.billing.credits import get_balance
from app.services.billing.exceptions import (
    BillingCycleMismatchError,
    BillingError,
    PriceUnresolvedError,
    WebhookSignatureError,
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
    days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days to pause; the service enforces 7..90.",
    )


class SubscriptionView(BaseModel):
    id: uuid.UUID
    plan: str
    billing_cycle: str
    llm_upgrade: str
    llm_upgrade_billing_cycle: str | None
    status: str
    trial_ends_at: datetime | None
    period_start: datetime
    period_end: datetime
    resumes_used: int
    searches_used: int
    upgraded_resumes_used: int
    cancel_at_period_end: bool
    payment_failed_at: datetime | None
    paused_at: datetime | None
    pause_resumes_at: datetime | None


class RefundRequestPayload(BaseModel):
    reason: Literal[
        "self_service_24h",
        "self_service_unused",
        "manual",
        "chargeback",
    ] = "manual"
    note: str = Field("", max_length=2000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    try:
        await sub_service.pause_subscription(db, user=user, days=payload.days)
    except ValueError as exc:
        # The service raises ValueError for both "no subscription" and
        # "days outside 7..90"; map to 400 for the validation case and
        # 404 for the missing case.  We disambiguate by the message
        # prefix.
        if "between" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_pause_days",
                    "min_days": settings.SUBSCRIPTION_PAUSE_MIN_DAYS,
                    "max_days": settings.SUBSCRIPTION_PAUSE_MAX_DAYS,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        )
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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_subscription"},
        )
    return {"ok": True, "pending_via_webhook": True}


@router.get("/api/subscriptions/current")
@limiter.limit("120/minute")
async def subscriptions_current(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionView | dict[str, None]:
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
        return {"subscription": None}
    return SubscriptionView(
        id=sub.id,
        plan=sub.plan.value,
        billing_cycle=sub.billing_cycle.value,
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
    )


@router.post("/api/subscriptions/llm-upgrade/checkout")
@limiter.limit("30/minute")
async def subscriptions_llm_upgrade_checkout(
    request: Request,
    payload: CheckoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CheckoutResponse:
    """LLM upgrade checkout — Step 19 ships the full pricing/routing logic.

    Step 6 wires up the route so the public route table is satisfied;
    Step 19 layers in the yearly-mismatch enforcement and Best soft-cap
    middleware.  Today this delegates to the same checkout helper.
    """
    base = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(
                Subscription.status.in_(
                    [
                        SubscriptionStatus.active,
                        SubscriptionStatus.trialing,
                        SubscriptionStatus.grace,
                        SubscriptionStatus.cancel_at_period_end,
                    ]
                )
            )
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    try:
        sub_service.assert_yearly_addon_alignment(
            addon_code=payload.code, base_subscription=base
        )
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


@router.post("/api/subscriptions/refund-request")
@limiter.limit("10/minute")
async def subscriptions_refund_request(
    request: Request,
    payload: RefundRequestPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Queue a manual refund request for super-admin review (§18.3).

    Stripe is *not* contacted from this route — admin approval flow in
    Step 35 issues the actual ``stripe.Refund.create`` call and writes
    the matching :class:`RefundRecord` plus :class:`CreditTransaction`
    reversal.  Here we just persist the user-facing request.
    """
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
        amount_usd=0,
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
    return await _persist_and_dispatch(db, event_dict, raw_body)


async def _persist_and_dispatch(
    db: AsyncSession, event: dict[str, Any], raw_body: bytes
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

    if inserted_id is None and row.status == StripeWebhookStatus.processed:
        # Pure duplicate — the handler ran successfully on a previous
        # delivery.  Return 200 immediately without touching anything.
        log.info(
            "billing.webhook.duplicate_processed_ack", event_id=event_id
        )
        return {"received": True, "duplicate": True}

    if row.attempts >= settings.STRIPE_WEBHOOK_MAX_ATTEMPTS:
        row.status = StripeWebhookStatus.needs_review
        await db.commit()
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
    except WebhookSignatureError as exc:
        # Should never reach here — signature was verified above.
        await db.rollback()
        await _mark_failed(db, row, str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_signature"},
        ) from exc
    except Exception as exc:  # noqa: BLE001 — webhook resilience
        await db.rollback()
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
