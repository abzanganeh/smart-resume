"""Free-tier AI spend cap — lifetime USD backstop for platform LLM calls."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import async_session_factory
from app.models.billing import CreditKind, Subscription, SubscriptionStatus
from app.models.user import CreditTransaction, User
from app.services.billing.credit_spend import spendable_free_credits
from app.services.billing.credits import get_balance
from app.services.billing.exceptions import FreeTierAiBudgetExceededError
from app.services.billing.tier_limits_lookup import registration_grant_credits
from app.services import session_store

log = structlog.get_logger("billing.free_tier_budget")

_LIFETIME_USD_KEY = "llm_usage:user:{user_id}:lifetime_usd"

# Explicit TTL on the lifetime counter. The cap is nominally "lifetime" but
# storing it in Redis means we must either (a) mark the key as persistent, or
# (b) pick a very long TTL so that under ``allkeys-lru`` / ``volatile-*``
# eviction policies the key is not silently cleared and turned into a bypass
# path. Chosen: 5 years.  The counter should migrate to Postgres once the
# free-tier cap becomes user-facing revenue policy.
_LIFETIME_TTL_SECONDS = 5 * 365 * 24 * 3600

# Per-request cache: once we've confirmed a user's paid-plan status for this
# request, skip the DB round-trip on every subsequent LLM call.  Cleared by
# the ``llm_accounting_context`` in ``token_accounting`` between requests.
_paid_plan_cache: ContextVar[dict[str, bool] | None] = ContextVar(
    "free_tier_paid_plan_cache", default=None
)


def _lifetime_key(user_id: str) -> str:
    return _LIFETIME_USD_KEY.format(user_id=user_id)


def _get_cache() -> dict[str, bool] | None:
    return _paid_plan_cache.get()


def reset_paid_plan_cache() -> None:
    """Install a fresh per-request paid-plan cache. Called by accounting ctx."""
    _paid_plan_cache.set({})


async def get_user_lifetime_usd(user_id: str) -> float:
    raw = await session_store.redis_get(_lifetime_key(user_id))
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


async def add_user_lifetime_usd(user_id: str, amount_usd: float) -> float:
    """Atomically increment lifetime platform AI spend; returns new total.

    Uses Redis ``INCRBYFLOAT`` so concurrent LLM calls for the same user
    cannot lose increments to a read-modify-write race.  Applies the long
    TTL on the (re)touched key so a slow user does not accidentally get
    their counter evicted.
    """
    if amount_usd <= 0:
        return await get_user_lifetime_usd(user_id)
    key = _lifetime_key(user_id)
    total = await session_store.redis_incrbyfloat(key, amount_usd)
    await session_store.redis_expire(key, _LIFETIME_TTL_SECONDS)
    return round(total, 6)


async def clear_user_lifetime_usd_for_tests(user_id: str) -> None:
    await session_store.redis_delete(_lifetime_key(user_id))


async def _active_subscription(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
    now = datetime.now(timezone.utc)
    sub = (
        await session.execute(
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
            .limit(1)
        )
    ).scalar_one_or_none()
    if sub is None or sub.status == SubscriptionStatus.paused:
        return None
    if not (sub.period_start <= now <= sub.period_end):
        return None
    return sub


async def user_on_paid_plan(session: AsyncSession, *, user_id: uuid.UUID) -> bool:
    return (await _active_subscription(session, user_id=user_id)) is not None


async def _cached_user_on_paid_plan(user_id: str) -> bool:
    """Per-request-cached paid-plan check to avoid a DB round-trip per LLM call."""
    cache = _get_cache()
    if cache is not None and user_id in cache:
        return cache[user_id]

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        result = False
    else:
        async with async_session_factory() as session:
            result = await user_on_paid_plan(session, user_id=uid)

    if cache is not None:
        cache[user_id] = result
    return result


async def assert_free_user_llm_allowed(user_id: str | None) -> None:
    """Block platform LLM when a free user's lifetime AI spend hits the cap.

    Raises :class:`FreeTierAiBudgetExceededError` (subclass of
    ``InsufficientCreditsError``) so callers can distinguish per-user
    cap exhaustion from platform-side provider quota exhaustion.
    """
    if not user_id or settings.FREE_TIER_MAX_USD <= 0:
        return
    try:
        uuid.UUID(user_id)
    except ValueError:
        return

    if await _cached_user_on_paid_plan(user_id):
        return

    lifetime = await get_user_lifetime_usd(user_id)
    if lifetime >= settings.FREE_TIER_MAX_USD:
        log.info(
            "free_tier_ai_budget_exceeded",
            user_id=user_id,
            lifetime_usd=lifetime,
            cap_usd=settings.FREE_TIER_MAX_USD,
        )
        raise FreeTierAiBudgetExceededError(
            cap_usd=settings.FREE_TIER_MAX_USD,
            used_usd=lifetime,
        )


async def record_free_tier_ai_spend(user_id: str, cost_usd: float) -> None:
    """Add ``cost_usd`` to the user's lifetime counter — free users only.

    Uses the per-request paid-plan cache so this does not add a DB session
    round-trip on top of every LLM call in a phase.  Called by
    ``token_accounting.record_llm_response`` after each provider response.
    """
    if cost_usd <= 0 or not user_id or settings.FREE_TIER_MAX_USD <= 0:
        return
    try:
        uuid.UUID(user_id)
    except ValueError:
        return
    if await _cached_user_on_paid_plan(user_id):
        return
    await add_user_lifetime_usd(user_id, cost_usd)


async def _total_free_credits_granted(
    session: AsyncSession, *, user_id: uuid.UUID
) -> int:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.credit_kind == CreditKind.free,
                CreditTransaction.delta > 0,
            )
        )
    ).scalar_one()
    grant = int(total or 0)
    if grant <= 0:
        grant = await registration_grant_credits(session)
    return max(grant, 0)


async def free_credit_meter(
    session: AsyncSession, *, user: User
) -> dict[str, int | bool]:
    """Return credit cap/used/spendable for the usage meter UI."""
    free_balance = await get_balance(session, user_id=user.id, credit_kind=CreditKind.free)
    cap = await _total_free_credits_granted(session, user_id=user.id)
    spendable = spendable_free_credits(user, balance=free_balance)
    used = max(0, cap - free_balance)
    return {
        "credit_cap": cap,
        "credits_used": used,
        "spendable_credit_balance": spendable,
        "credits_locked_until_verification": free_balance > 0
        and not user.is_email_verified,
    }


__all__ = [
    "add_user_lifetime_usd",
    "assert_free_user_llm_allowed",
    "clear_user_lifetime_usd_for_tests",
    "free_credit_meter",
    "get_user_lifetime_usd",
    "record_free_tier_ai_spend",
    "reset_paid_plan_cache",
    "user_on_paid_plan",
]
