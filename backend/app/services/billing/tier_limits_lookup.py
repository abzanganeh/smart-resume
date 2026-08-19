"""Load active tier limits from ``tier_limits_config`` with seed fallback."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tier_limits import TierLimitsConfig
from app.services.billing.tier_limits import seed_row_for_plan


@dataclass(frozen=True, slots=True)
class TierLimits:
    plan_code: str
    resumes_per_period: int
    cover_letters_per_period: int
    searches_per_period: int
    fit_analyses_per_period: int
    checkups_per_period: int | None
    story_sessions: int | None
    coached_sessions: int | None
    whisper_enabled: bool
    whisper_uses_per_period: int | None
    # Max non-archived rows a user may keep in the application tracker.
    # ``None`` means no active-slot cap for this plan (still subject to
    # per-period counters and credits).
    tracker_active_limit: int | None
    soft_cap_message: str | None


def _from_seed(plan_code: str) -> TierLimits:
    row = seed_row_for_plan(plan_code)
    if row is None:
        raise ValueError(f"unknown plan_code: {plan_code!r}")
    return TierLimits(
        plan_code=row["plan_code"],
        resumes_per_period=row["resumes_per_period"],
        cover_letters_per_period=row["cover_letters_per_period"],
        searches_per_period=row["searches_per_period"],
        fit_analyses_per_period=row["fit_analyses_per_period"],
        checkups_per_period=row["checkups_per_period"],
        story_sessions=row["story_sessions"],
        coached_sessions=row["coached_sessions"],
        whisper_enabled=row["whisper_enabled"],
        whisper_uses_per_period=row["whisper_uses_per_period"],
        tracker_active_limit=row["tracker_active_limit"],
        soft_cap_message=row["soft_cap_message"],
    )


def _from_row(row: TierLimitsConfig) -> TierLimits:
    return TierLimits(
        plan_code=row.plan_code,
        resumes_per_period=row.resumes_per_period,
        cover_letters_per_period=row.cover_letters_per_period,
        searches_per_period=row.searches_per_period,
        fit_analyses_per_period=row.fit_analyses_per_period,
        checkups_per_period=row.checkups_per_period,
        story_sessions=row.story_sessions,
        coached_sessions=row.coached_sessions,
        whisper_enabled=row.whisper_enabled,
        whisper_uses_per_period=row.whisper_uses_per_period,
        tracker_active_limit=row.tracker_active_limit,
        soft_cap_message=row.soft_cap_message,
    )


async def get_active_tier_limits(
    session: AsyncSession, plan_code: str
) -> TierLimits:
    """Return the active admin row for ``plan_code``, else seeded defaults."""
    stmt = (
        select(TierLimitsConfig)
        .where(TierLimitsConfig.plan_code == plan_code)
        .where(TierLimitsConfig.is_active.is_(True))
        .order_by(TierLimitsConfig.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return _from_row(row)
    return _from_seed(plan_code)


async def registration_grant_credits(session: AsyncSession) -> int:
    """Free-tier registration grant from active admin config or seed fallback."""
    limits = await get_active_tier_limits(session, "free")
    return limits.resumes_per_period


__all__ = [
    "TierLimits",
    "get_active_tier_limits",
    "registration_grant_credits",
]
