"""Global seed poll scheduling by priority tier (15 / 30 / 45 min)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.career_watch import WatchedCompany
from app.services.career_watch.poll_schedule import is_poll_due


def interval_minutes_for_tier(tier: int | None) -> int:
    """Map poll_priority_tier to interval minutes."""
    if tier == 1:
        return settings.GLOBAL_POLL_INTERVAL_TIER_1_MINUTES
    if tier == 2:
        return settings.GLOBAL_POLL_INTERVAL_TIER_2_MINUTES
    if tier == 3:
        return settings.GLOBAL_POLL_INTERVAL_TIER_3_MINUTES
    return settings.GLOBAL_POLL_INTERVAL_TIER_2_MINUTES


async def fetch_due_global_seeds(
    session: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> list[WatchedCompany]:
    """Return active global seed companies due for tiered polling."""
    now_dt = now or datetime.now(timezone.utc)
    stmt = (
        select(WatchedCompany)
        .where(WatchedCompany.is_active.is_(True))
        .where(WatchedCompany.is_global_seed.is_(True))
        .order_by(WatchedCompany.last_polled_at.asc().nullsfirst())
    )
    candidates = list((await session.execute(stmt)).scalars())
    due: list[WatchedCompany] = []
    for company in candidates:
        interval = interval_minutes_for_tier(company.poll_priority_tier)
        if is_poll_due(company.last_polled_at, interval, now=now_dt):
            due.append(company)
        if len(due) >= limit:
            break
    return due


__all__ = [
    "fetch_due_global_seeds",
    "interval_minutes_for_tier",
]
