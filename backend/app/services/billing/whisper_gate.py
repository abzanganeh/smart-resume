"""Tier-based Whisper transcription gate (pricing restructure slice 6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Subscription, SubscriptionStatus
from app.models.user import User
from app.services.billing.exceptions import (
    AccountSuspendedError,
    PlanLimitReachedError,
    WhisperNotAllowedError,
)
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.quota import QuotaAction, QuotaDecision, _active_subscription_for
from app.services.billing.tier_limits_lookup import TierLimits, get_active_tier_limits


@dataclass(frozen=True, slots=True)
class WhisperEntitlement:
    enabled: bool
    limit: int | None
    used: int
    remaining: int | None
    plan_code: str


async def _resolve_limits_for_user(
    session: AsyncSession, user: User
) -> tuple[TierLimits, Subscription | None, int]:
    sub = await _active_subscription_for(session, user_id=user.id)
    now = datetime.now(timezone.utc)
    limits = await get_active_tier_limits(
        session, await resolve_plan_code_for_user(session, user, now=now)
    )
    if sub is not None and sub.period_start <= now <= sub.period_end:
        if sub.status != SubscriptionStatus.paused:
            return limits, sub, sub.whisper_uses_used
    return limits, None, 0


async def whisper_entitlement_for_user(
    session: AsyncSession, *, user: User
) -> WhisperEntitlement:
    limits, _sub, used = await _resolve_limits_for_user(session, user)
    limit = limits.whisper_uses_per_period
    if not limits.whisper_enabled:
        remaining = 0
    elif limit is None:
        remaining = None
    else:
        remaining = max(0, limit - used)
    return WhisperEntitlement(
        enabled=limits.whisper_enabled,
        limit=limit,
        used=used,
        remaining=remaining,
        plan_code=limits.plan_code,
    )


async def check_and_increment_whisper_use(
    session: AsyncSession,
    *,
    user: User,
) -> QuotaDecision:
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    limits, sub, used = await _resolve_limits_for_user(session, user)
    if not limits.whisper_enabled:
        raise WhisperNotAllowedError(plan_code=limits.plan_code)

    limit = limits.whisper_uses_per_period
    if limit is not None and used >= limit:
        raise PlanLimitReachedError("whisper_transcription", used, limit)

    if sub is not None:
        sub.whisper_uses_used = used + 1
        await session.flush()
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="subscription_whisper",
            subscription_id=sub.id,
        )

    raise WhisperNotAllowedError(plan_code=limits.plan_code)


__all__ = [
    "WhisperEntitlement",
    "check_and_increment_whisper_use",
    "whisper_entitlement_for_user",
]
