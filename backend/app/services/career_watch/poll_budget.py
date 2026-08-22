"""Global daily poll budget with tier-3-first backpressure."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.career_watch import WatchedCompany


def _utc_day_start(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def count_polls_today(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    """Count company polls completed since UTC midnight."""
    now_dt = now or datetime.now(timezone.utc)
    day_start = _utc_day_start(now_dt)
    stmt = (
        select(func.count())
        .select_from(WatchedCompany)
        .where(WatchedCompany.last_polled_at.is_not(None))
        .where(WatchedCompany.last_polled_at >= day_start)
    )
    return int((await session.execute(stmt)).scalar_one())


def _drop_priority(company: WatchedCompany) -> int:
    """Lower values are dropped first when the daily budget is tight."""
    if not company.is_global_seed:
        return 100
    tier = company.poll_priority_tier or 2
    if tier == 3:
        return 0
    if tier == 2:
        return 1
    return 2


def apply_daily_poll_budget(
    companies: list[WatchedCompany],
    *,
    polls_today: int,
    budget: int | None = None,
) -> list[WatchedCompany]:
    """Trim ``companies`` to fit the remaining daily poll budget.

    Global tier-3 seeds are skipped first, then tier-2, while user-watch
    companies and tier-1 global seeds are preserved as long as possible.
    """
    cap = budget if budget is not None else settings.GLOBAL_POLL_DAILY_BUDGET
    if cap <= 0:
        return companies
    remaining = max(0, cap - polls_today)
    if len(companies) <= remaining:
        return companies

    ranked = sorted(
        companies,
        key=lambda company: (_drop_priority(company), company.last_polled_at or datetime.min),
        reverse=True,
    )
    return ranked[:remaining]


__all__ = [
    "apply_daily_poll_budget",
    "count_polls_today",
]
