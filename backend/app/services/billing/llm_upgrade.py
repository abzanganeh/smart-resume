"""LLM upgrade tier resolution + Phase 3 routing helpers (Step 19).

Single source of truth for the routing tree applied before the Phase 3
LLM call:

```
preferred_tier (from request)
  └─ entitled_tier = get_user_phase3_tier(user_id)
        - "best"     → active best_monthly/best_yearly subscription AND
                       upgraded_resumes_used < 100
        - "better"   → active better_monthly/better_yearly subscription
                       OR CreditTransaction(credit_kind="better") balance > 0
        - "standard" → no upgrade (or best soft cap hit)
```

When the *requested* tier exceeds the entitlement we silently fall back
to the highest tier the user is entitled to.  The orchestrator emits a
``best_soft_cap_hit`` SSE event when the soft cap is reached so the
frontend can surface a banner.

Pricing prices (§18.3 / §18.9):
- ``better_5pack``      $4.49 / 5-pack (~$0.898 / resume)
- ``better_monthly``    +$4.99 / mo
- ``better_yearly``     +$47.90 / yr
- ``best_per_resume``   $2.99 / resume
- ``best_monthly``      +$12.99 / mo
- ``best_yearly``       +$124.99 / yr

These literals live in ``billing/price_resolver.py`` (env vars) and
``PlanConfig`` rows; this module never references them directly.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditKind,
    LLMUpgradeTier,
    Subscription,
    SubscriptionStatus,
)
from app.models.llm_config import LLMConfig, LLMProvider
from app.services.billing.credits import consume_credit, get_balance

log = structlog.get_logger("billing.llm_upgrade")


# §18.3 hard ceiling on Best add-on usage per period.  Runs 101–150
# silently fall back to Standard with a UI banner.
BEST_SUBSCRIPTION_SOFT_CAP: int = 100


# Hardcoded fallback used only when ``llm_configs`` is empty and the
# bootstrap seed has not run.  The orchestrator must still resolve to
# *something* in that pathological case (e.g. fresh local dev).
# IMPORTANT: never hardcode model strings outside this fallback — read
# from :class:`LLMConfig` via :func:`resolve_phase3_model`.
_FALLBACK_MODELS: dict[LLMUpgradeTier, tuple[LLMProvider, str]] = {
    LLMUpgradeTier.standard: (LLMProvider.gemini, "gemini-2.5-flash-lite"),
    LLMUpgradeTier.better: (LLMProvider.gemini, "gemini-2.5-flash"),
    LLMUpgradeTier.best: (LLMProvider.anthropic, "claude-sonnet-4-6"),
}


# Literal alias used by the public surface so callers can pass plain
# strings without importing the SQLAlchemy enum.
TierLiteral = Literal["standard", "better", "best"]


class Phase3TierError(enum.Enum):
    """Reason codes returned alongside the resolved tier when the
    requested tier had to be downgraded.

    Surfaced to the frontend so it can show the right banner / 402
    upgrade prompt:

    - ``not_entitled_better`` → user picked Better but has no active
      Better subscription nor any Better credit balance.
    - ``not_entitled_best``   → user picked Best but has no active
      Best subscription.
    - ``best_soft_cap_hit``   → user has Best subscription but burned
      through 100 upgraded resumes this period.
    """

    not_entitled_better = "not_entitled_better"
    not_entitled_best = "not_entitled_best"
    best_soft_cap_hit = "best_soft_cap_hit"


@dataclass(frozen=True, slots=True)
class TierStatus:
    """Read-only view of a user's LLM upgrade entitlements.

    Used by ``GET /api/subscriptions/llm-upgrade/status`` so the
    frontend can render the selector with the right credit / soft-cap
    badges and gate yearly options on the base subscription cycle.
    """

    entitled_tier: TierLiteral
    better_subscription_active: bool
    best_subscription_active: bool
    better_credits_balance: int
    upgraded_resumes_used: int
    upgraded_resumes_limit: int
    best_soft_cap_hit: bool
    base_billing_cycle: Optional[str]  # "recurring" | "yearly" | None


@dataclass(frozen=True, slots=True)
class Phase3RouteDecision:
    """Resolved routing for a single Phase 3 run.

    - ``effective_tier``  — the tier the LLM call will actually use.
    - ``provider``        — provider id passed to ``get_llm_client``.
    - ``model_string``    — model id passed to ``get_llm_client``.
    - ``soft_cap_hit``    — true when Best subscription was downgraded
                            because the period counter reached 100.
    - ``downgrade_reason``— set when the requested tier was higher than
                            the entitlement; the orchestrator emits a
                            matching SSE event so the UI can prompt the
                            user to top up.
    """

    effective_tier: TierLiteral
    provider: str
    model_string: str
    soft_cap_hit: bool = False
    downgrade_reason: Optional[Phase3TierError] = None
    consumed_credit_id: Optional[uuid.UUID] = None
    incremented_subscription_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Subscription lookups
# ---------------------------------------------------------------------------


async def _entitled_subscriptions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    for_update: bool = False,
) -> list[Subscription]:
    """Return all currently entitled subscription rows for ``user_id``.

    Includes both base plan subscriptions and add-on subscriptions —
    the caller filters by ``llm_upgrade`` to find the LLM tier rows.

    "Entitled" mirrors §7.7: status ∈ {active, trialing, grace,
    cancel_at_period_end}.  Paused / expired do not count.
    """
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
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
        .order_by(Subscription.created_at.desc())
    )
    if for_update:
        stmt = stmt.with_for_update()
    return list((await session.execute(stmt)).scalars().all())


def _is_within_period(sub: Subscription, *, now: datetime) -> bool:
    return sub.period_start <= now <= sub.period_end


def _find_addon_for(
    subs: list[Subscription], *, tier: LLMUpgradeTier, now: datetime
) -> Subscription | None:
    """Return the active add-on subscription matching ``tier``.

    A subscription is treated as the LLM upgrade carrier when its
    ``llm_upgrade`` column equals ``tier`` (the webhook handler sets
    this when the price id resolves to ``better_*`` / ``best_*``
    add-on codes — see ``billing/webhook_handler.py::_classify_code``).
    """
    for sub in subs:
        if sub.llm_upgrade != tier:
            continue
        if not _is_within_period(sub, now=now):
            continue
        return sub
    return None


def _find_best_subscription(
    subs: list[Subscription], *, now: datetime
) -> Subscription | None:
    return _find_addon_for(subs, tier=LLMUpgradeTier.best, now=now)


def _find_better_subscription(
    subs: list[Subscription], *, now: datetime
) -> Subscription | None:
    return _find_addon_for(subs, tier=LLMUpgradeTier.better, now=now)


def _base_billing_cycle(subs: list[Subscription], *, now: datetime) -> str | None:
    """Return the base subscription's billing cycle (``recurring`` /
    ``yearly``), or None if the user has no active base subscription.

    Used by the yearly add-on eligibility gate (§7.7) — the frontend
    only shows the yearly add-on option when the base cycle is yearly.
    """
    for sub in subs:
        if sub.llm_upgrade != LLMUpgradeTier.standard:
            # Add-on rows carry ``llm_upgrade != standard``; skip those
            # when looking for the user's base plan.
            continue
        if not _is_within_period(sub, now=now):
            continue
        return sub.billing_cycle.value
    # Fallback: if we couldn't disambiguate, return the most recent
    # active subscription's cycle (single-row case where no add-on
    # has ever been bought).
    if subs:
        return subs[0].billing_cycle.value
    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


async def get_user_phase3_tier(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> TierLiteral:
    """Return the user's currently active Phase 3 tier.

    Precedence: ``best`` > ``better`` > ``standard``.

    - "best"     when an active Best add-on subscription is in period
                 AND ``upgraded_resumes_used < 100``.  When the soft
                 cap is hit we return ``"standard"`` (the
                 :func:`get_phase3_tier_status` helper carries the
                 explicit ``best_soft_cap_hit`` flag for the UI).
    - "better"   when an active Better add-on subscription is in
                 period OR the user has any Better credit balance > 0.
    - "standard" otherwise.
    """
    status = await get_phase3_tier_status(session, user_id=user_id)
    return status.entitled_tier


async def get_phase3_tier_status(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> TierStatus:
    """Return a structured view of the user's LLM upgrade entitlements."""
    now = datetime.now(timezone.utc)
    subs = await _entitled_subscriptions(session, user_id=user_id)

    best_sub = _find_best_subscription(subs, now=now)
    best_subscription_active = best_sub is not None
    upgraded_used = best_sub.upgraded_resumes_used if best_sub else 0
    soft_cap_hit = (
        best_sub is not None
        and best_sub.upgraded_resumes_used >= BEST_SUBSCRIPTION_SOFT_CAP
    )

    better_sub = _find_better_subscription(subs, now=now)
    better_credits = await get_balance(
        session,
        user_id=user_id,
        credit_kind=CreditKind.better,
        for_share=False,
    )

    if best_subscription_active and not soft_cap_hit:
        entitled: TierLiteral = "best"
    elif better_sub is not None or better_credits > 0:
        entitled = "better"
    else:
        entitled = "standard"

    return TierStatus(
        entitled_tier=entitled,
        better_subscription_active=better_sub is not None,
        best_subscription_active=best_subscription_active,
        better_credits_balance=better_credits,
        upgraded_resumes_used=upgraded_used,
        upgraded_resumes_limit=BEST_SUBSCRIPTION_SOFT_CAP,
        best_soft_cap_hit=soft_cap_hit,
        base_billing_cycle=_base_billing_cycle(subs, now=now),
    )


async def resolve_phase3_model(
    session: AsyncSession,
    tier: TierLiteral | LLMUpgradeTier,
) -> tuple[str, str]:
    """Return ``(provider, model_string)`` for ``tier``.

    Reads from the active :class:`LLMConfig` row whose ``tier`` matches.
    Falls back to the canonical defaults documented in §18.9 only when
    no row exists (fresh DB before the boot-time seed has run).

    Raises :class:`KeyError` when ``tier`` is not a valid value.
    """
    enum_tier = (
        tier
        if isinstance(tier, LLMUpgradeTier)
        else LLMUpgradeTier(tier)
    )
    row = (
        await session.execute(
            select(LLMConfig)
            .where(LLMConfig.tier == enum_tier)
            .where(LLMConfig.is_active.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.provider.value, row.model_string

    log.warning(
        "billing.llm_upgrade.fallback_default_model",
        tier=enum_tier.value,
        reason="no_active_llm_config_row",
    )
    provider, model = _FALLBACK_MODELS[enum_tier]
    return provider.value, model


# ---------------------------------------------------------------------------
# Phase 3 routing middleware (used by the orchestrator)
# ---------------------------------------------------------------------------


async def apply_phase3_tier(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    requested_tier: TierLiteral,
    related_resume_record_id: uuid.UUID | None = None,
    session_id: str | None = None,
) -> Phase3RouteDecision:
    """Resolve the effective tier for one Phase 3 run and apply the
    corresponding accounting side-effects atomically.

    - ``standard``: no entitlement check, no consumption.
    - ``better``:   serializes on the Better balance projection via
                    ``consume_credit`` (raises
                    :class:`InsufficientCreditsError` when the balance
                    is zero — caller surfaces 402).  Counter for the
                    Better add-on subscription is *not* incremented;
                    Better access is credit-based per §7.5.
                    For an entitled Better-subscription user we still
                    consume one credit row from the ``better`` ledger
                    so usage tracking is uniform — runs that want
                    "subscription mirrors free quota" semantics should
                    instead grant Better credits at period rollover.
    - ``best``:     locks the Best add-on subscription row with
                    ``SELECT … FOR UPDATE`` and increments
                    ``upgraded_resumes_used`` if below the soft cap.
                    On cap hit we return a downgrade decision; the
                    orchestrator emits ``best_soft_cap_hit`` SSE.

    The caller is responsible for committing the surrounding
    transaction.  When this function raises everything is rolled back
    atomically so the credit / counter is never lost.
    """
    requested = _normalize_tier(requested_tier)
    if requested == "standard":
        provider, model = await resolve_phase3_model(session, "standard")
        return Phase3RouteDecision(
            effective_tier="standard",
            provider=provider,
            model_string=model,
        )

    now = datetime.now(timezone.utc)
    subs = await _entitled_subscriptions(
        session, user_id=user_id, for_update=True
    )
    better_sub = _find_better_subscription(subs, now=now)
    best_sub = _find_best_subscription(subs, now=now)
    better_balance = await get_balance(
        session, user_id=user_id, credit_kind=CreditKind.better, for_share=False
    )

    if requested == "best":
        if best_sub is None:
            log.info(
                "billing.llm_upgrade.best_not_entitled",
                user_id=str(user_id),
            )
            # Downgrade to Better when available (entitlement precedence:
            # best -> better -> standard). This prevents routing leaks where
            # a user asks for Best but is only entitled to Better.
            if better_sub is not None or better_balance > 0:
                requested = "better"
            else:
                return await _fallback_to_standard(
                    session, reason=Phase3TierError.not_entitled_best
                )
        if best_sub is not None:
            if best_sub.upgraded_resumes_used >= BEST_SUBSCRIPTION_SOFT_CAP:
                log.info(
                    "billing.llm_upgrade.best_soft_cap_hit",
                    user_id=str(user_id),
                    used=best_sub.upgraded_resumes_used,
                    cap=BEST_SUBSCRIPTION_SOFT_CAP,
                )
                return await _fallback_to_standard(
                    session,
                    reason=Phase3TierError.best_soft_cap_hit,
                    soft_cap_hit=True,
                )
            best_sub.upgraded_resumes_used += 1
            await session.flush()
            provider, model = await resolve_phase3_model(session, "best")
            return Phase3RouteDecision(
                effective_tier="best",
                provider=provider,
                model_string=model,
                incremented_subscription_id=best_sub.id,
            )

    # requested == "better"
    if better_sub is None and better_balance <= 0:
        log.info(
            "billing.llm_upgrade.better_not_entitled",
            user_id=str(user_id),
        )
        return await _fallback_to_standard(
            session, reason=Phase3TierError.not_entitled_better
        )

    # Better path: consume one credit (or grant + consume implicit
    # subscription credit by maintaining a single Better balance source
    # of truth).  When the user holds a Better subscription but no
    # ledger balance the run should still proceed; we add a +1 / -1
    # pair so the ledger row history records the subscription debit
    # without exposing inflated balances.
    if better_balance <= 0 and better_sub is not None:
        from app.services.billing.credits import grant_credit

        await grant_credit(
            session,
            user_id=user_id,
            credit_kind=CreditKind.better,
            delta=1,
            reason="better_subscription_period_run",
            related_subscription_id=better_sub.id,
        )

    consumed = await consume_credit(
        session,
        user_id=user_id,
        credit_kind=CreditKind.better,
        reason="phase3_run_better",
        session_id=session_id,
        related_resume_record_id=related_resume_record_id,
    )
    provider, model = await resolve_phase3_model(session, "better")
    return Phase3RouteDecision(
        effective_tier="better",
        provider=provider,
        model_string=model,
        consumed_credit_id=consumed.id,
    )


async def _fallback_to_standard(
    session: AsyncSession,
    *,
    reason: Phase3TierError,
    soft_cap_hit: bool = False,
) -> Phase3RouteDecision:
    provider, model = await resolve_phase3_model(session, "standard")
    return Phase3RouteDecision(
        effective_tier="standard",
        provider=provider,
        model_string=model,
        soft_cap_hit=soft_cap_hit,
        downgrade_reason=reason,
    )


def _normalize_tier(value: TierLiteral | str | None) -> TierLiteral:
    if value is None:
        return "standard"
    if value not in {"standard", "better", "best"}:
        return "standard"
    return value  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Bootstrap seed (called from ``app/main.py`` lifespan)
# ---------------------------------------------------------------------------


_DEFAULT_LLM_CONFIGS: list[dict] = [
    {
        "tier": LLMUpgradeTier.standard,
        "provider": LLMProvider.gemini,
        "model_string": "gemini-2.5-flash-lite",
        "phases_enabled": ["1", "2", "3", "4", "fit", "cover_letter"],
        "notes": "§18.9 default — covers every phase unless an upgrade is active.",
    },
    {
        "tier": LLMUpgradeTier.better,
        "provider": LLMProvider.gemini,
        "model_string": "gemini-2.5-flash",
        "phases_enabled": ["3"],
        "notes": "§18.9 Better — Phase 3 only; $4.49/5-pack or +$4.99/mo.",
    },
    {
        "tier": LLMUpgradeTier.best,
        "provider": LLMProvider.anthropic,
        "model_string": "claude-sonnet-4-6",
        "phases_enabled": ["3"],
        "notes": "§18.9 Best — Phase 3 only; $2.99/resume or +$12.99/mo.",
    },
]


async def seed_llm_configs_if_empty(session: AsyncSession) -> int:
    """Insert one ``LLMConfig`` row per tier; no-op if any already exists."""
    from sqlalchemy import func

    count = (
        await session.execute(select(func.count()).select_from(LLMConfig))
    ).scalar() or 0
    if count > 0:
        log.info("billing.llm_upgrade.configs_already_seeded", count=count)
        return 0

    inserted = 0
    for cfg in _DEFAULT_LLM_CONFIGS:
        row = LLMConfig(
            id=uuid.uuid4(),
            tier=cfg["tier"],
            provider=cfg["provider"],
            model_string=cfg["model_string"],
            phases_enabled=list(cfg["phases_enabled"]),
            is_active=True,
            notes=cfg.get("notes"),
            created_by_admin_id=None,
        )
        session.add(row)
        inserted += 1
    await session.flush()
    log.info("billing.llm_upgrade.configs_seeded", inserted=inserted)
    return inserted


# ---------------------------------------------------------------------------
# Code aliasing for the spec-canonical names accepted at the public API.
# ---------------------------------------------------------------------------


# IMPLEMENTATION_PLAN §7.1 / SYSTEM_DESIGN_PHASE_2 §18.3 use
# ``better_5pack`` as the canonical code; the existing webhook handler
# and price resolver carry the legacy ``better_pack`` alias.  The
# ``/api/subscriptions/llm-upgrade/checkout`` route accepts either and
# we collapse to the existing internal name here so the rest of the
# pipeline does not need to change.
_LLM_UPGRADE_CODE_ALIASES: dict[str, str] = {
    "better_5pack": "better_pack",
}


def normalize_llm_upgrade_code(code: str) -> str:
    """Translate spec-canonical codes into the legacy internal codes.

    Idempotent — passing an internal code returns it unchanged.
    """
    return _LLM_UPGRADE_CODE_ALIASES.get(code, code)


VALID_LLM_UPGRADE_CODES: frozenset[str] = frozenset(
    {
        "better_5pack",
        "better_monthly",
        "better_yearly",
        "best_per_resume",
        "best_monthly",
        "best_yearly",
    }
)


__all__ = [
    "BEST_SUBSCRIPTION_SOFT_CAP",
    "Phase3RouteDecision",
    "Phase3TierError",
    "TierStatus",
    "VALID_LLM_UPGRADE_CODES",
    "apply_phase3_tier",
    "get_phase3_tier_status",
    "get_user_phase3_tier",
    "normalize_llm_upgrade_code",
    "resolve_phase3_model",
    "seed_llm_configs_if_empty",
]
