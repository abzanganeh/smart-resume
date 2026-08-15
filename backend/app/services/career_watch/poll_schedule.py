"""Per-company Career Watch poll scheduling from watcher tier limits."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import UserWatchedCompany, WatchedCompany
from app.models.tier_limits import TierLimitsConfig
from app.models.user import User
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.tier_limits import get_seed_rows


def interval_for_plan_code(plan_code: str, interval_by_plan: dict[str, int]) -> int:
    """Map a plan code to poll interval minutes (defaults to free tier)."""
    if plan_code in interval_by_plan:
        return interval_by_plan[plan_code]
    free = interval_by_plan.get("free")
    if free is not None:
        return free
    return 30


def min_interval_for_plan_codes(
    plan_codes: Iterable[str],
    interval_by_plan: dict[str, int],
) -> int | None:
    """Return the minimum poll interval across ``plan_codes``, or ``None`` if empty."""
    codes = list(plan_codes)
    if not codes:
        return None
    return min(interval_for_plan_code(code, interval_by_plan) for code in codes)


def is_poll_due(
    last_polled_at: datetime | None,
    interval_minutes: int,
    *,
    now: datetime,
) -> bool:
    """``True`` when ``last_polled_at`` is older than ``interval_minutes``."""
    if last_polled_at is None:
        return True
    cutoff = now - timedelta(minutes=interval_minutes)
    if last_polled_at.tzinfo is None:
        last_polled_at = last_polled_at.replace(tzinfo=timezone.utc)
    return last_polled_at <= cutoff


async def load_interval_minutes_by_plan_code(
    session: AsyncSession,
) -> dict[str, int]:
    """Load ``plan_code -> career_watch_interval_minutes`` from seed + active DB rows."""
    intervals = {
        row["plan_code"]: row["career_watch_interval_minutes"] for row in get_seed_rows()
    }
    stmt = select(TierLimitsConfig).where(TierLimitsConfig.is_active.is_(True))
    for row in (await session.execute(stmt)).scalars():
        intervals[row.plan_code] = row.career_watch_interval_minutes
    return intervals


async def resolve_plan_codes_for_users(
    session: AsyncSession,
    user_ids: Iterable[uuid.UUID],
    *,
    now: datetime | None = None,
) -> dict[uuid.UUID, str]:
    """Resolve effective tier plan codes for ``user_ids``."""
    now_dt = now or datetime.now(timezone.utc)
    plan_by_user: dict[uuid.UUID, str] = {}
    for user_id in user_ids:
        user = await session.get(User, user_id)
        if user is None:
            continue
        plan_by_user[user_id] = await resolve_plan_code_for_user(
            session, user, now=now_dt
        )
    return plan_by_user


async def build_company_min_intervals(
    session: AsyncSession,
    *,
    interval_by_plan: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict[uuid.UUID, int]:
    """Map ``watched_company_id`` to min poll interval from active watchers."""
    if interval_by_plan is None:
        interval_by_plan = await load_interval_minutes_by_plan_code(session)

    stmt = (
        select(UserWatchedCompany.watched_company_id, UserWatchedCompany.user_id)
        .where(UserWatchedCompany.is_active.is_(True))
    )
    company_users: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    all_user_ids: set[uuid.UUID] = set()
    for company_id, user_id in (await session.execute(stmt)).all():
        company_users[company_id].add(user_id)
        all_user_ids.add(user_id)

    plan_by_user = await resolve_plan_codes_for_users(
        session, all_user_ids, now=now
    )

    result: dict[uuid.UUID, int] = {}
    for company_id, user_ids in company_users.items():
        plan_codes = [
            plan_by_user[user_id]
            for user_id in user_ids
            if user_id in plan_by_user
        ]
        interval = min_interval_for_plan_codes(plan_codes, interval_by_plan)
        if interval is not None:
            result[company_id] = interval
    return result


async def fetch_due_companies(
    session: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> list[WatchedCompany]:
    """Return active companies due for polling based on watcher tier intervals."""
    now_dt = now or datetime.now(timezone.utc)
    interval_by_plan = await load_interval_minutes_by_plan_code(session)
    min_intervals = await build_company_min_intervals(
        session, interval_by_plan=interval_by_plan, now=now_dt
    )
    if not min_intervals:
        return []

    stmt = (
        select(WatchedCompany)
        .where(WatchedCompany.is_active.is_(True))
        .where(WatchedCompany.id.in_(min_intervals.keys()))
        .order_by(WatchedCompany.last_polled_at.asc().nullsfirst())
    )
    candidates = list((await session.execute(stmt)).scalars())

    due: list[WatchedCompany] = []
    for company in candidates:
        interval = min_intervals.get(company.id)
        if interval is None:
            continue
        if is_poll_due(company.last_polled_at, interval, now=now_dt):
            due.append(company)
        if len(due) >= limit:
            break
    return due


__all__ = [
    "build_company_min_intervals",
    "fetch_due_companies",
    "interval_for_plan_code",
    "is_poll_due",
    "load_interval_minutes_by_plan_code",
    "min_interval_for_plan_codes",
    "resolve_plan_codes_for_users",
]
