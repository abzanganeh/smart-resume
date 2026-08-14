"""Career Watch tier limit helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tier_limits import TierLimitsConfig
from app.models.user import User
from app.models.career_watch import UserWatchedCompany
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.tier_limits import seed_row_for_plan


class CareerWatchLimitError(Exception):
    def __init__(self, *, limit: int, current: int) -> None:
        self.limit = limit
        self.current = current
        super().__init__(f"career watch company limit reached ({current}/{limit})")


async def _plan_code_for_user(session: AsyncSession, user: User) -> str:
    return await resolve_plan_code_for_user(session, user)


async def get_career_watch_limits(
    session: AsyncSession, *, user: User
) -> tuple[int, int]:
    """Return ``(max_companies, poll_interval_minutes)`` for ``user``."""
    plan_code = await _plan_code_for_user(session, user)
    stmt = (
        select(TierLimitsConfig)
        .where(TierLimitsConfig.plan_code == plan_code)
        .where(TierLimitsConfig.is_active.is_(True))
        .order_by(TierLimitsConfig.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row.career_watch_companies, row.career_watch_interval_minutes
    seed = seed_row_for_plan(plan_code) or seed_row_for_plan("free")
    assert seed is not None
    return seed["career_watch_companies"], seed["career_watch_interval_minutes"]


async def count_active_watches(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(UserWatchedCompany)
        .where(UserWatchedCompany.user_id == user_id)
        .where(UserWatchedCompany.is_active.is_(True))
    )
    return int((await session.execute(stmt)).scalar() or 0)


async def assert_can_add_watch(session: AsyncSession, *, user: User) -> None:
    limit, _ = await get_career_watch_limits(session, user=user)
    current = await count_active_watches(session, user_id=user.id)
    if current >= limit:
        raise CareerWatchLimitError(limit=limit, current=current)


__all__ = [
    "CareerWatchLimitError",
    "assert_can_add_watch",
    "count_active_watches",
    "get_career_watch_limits",
]
