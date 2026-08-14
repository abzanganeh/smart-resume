"""Resolve effective ``plan_code`` for a user (subscription + admin grants)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.billing import Subscription, SubscriptionStatus
from app.models.user import User
from app.services.billing.plan_code import resolve_plan_code_for_subscription
from app.services.billing.price_resolver import reverse_lookup_code


def _within_period(sub: Subscription, *, now: datetime) -> bool:
    return sub.period_start <= now <= sub.period_end


async def _active_subscription_for(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
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
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _active_tier_override_plan_code(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> str | None:
    stmt = (
        select(AdminUserGrant)
        .where(AdminUserGrant.user_id == user_id)
        .where(AdminUserGrant.grant_type == AdminGrantType.tier_override)
        .where(AdminUserGrant.revoked_at.is_(None))
        .order_by(AdminUserGrant.created_at.desc())
    )
    for grant in (await session.execute(stmt)).scalars():
        if grant.expires_at is not None and grant.expires_at <= now:
            continue
        plan_code = grant.payload.get("plan_code")
        if isinstance(plan_code, str) and plan_code.strip():
            return plan_code.strip()
    return None


async def resolve_plan_code_for_user(
    session: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> str:
    """Effective tier-limits plan code for ``user``."""
    now_dt = now or datetime.now(timezone.utc)
    override = await _active_tier_override_plan_code(
        session, user_id=user.id, now=now_dt
    )
    if override is not None:
        return override

    sub = await _active_subscription_for(session, user_id=user.id)
    if sub is None or sub.status == SubscriptionStatus.paused:
        return "free"
    if not _within_period(sub, now=now_dt):
        return "free"

    plan_config_code = await reverse_lookup_code(session, sub.stripe_price_id)
    return resolve_plan_code_for_subscription(sub, plan_config_code=plan_config_code)


async def resolve_plan_code_for_subscription_row(
    session: AsyncSession,
    sub: Subscription,
    *,
    now: datetime | None = None,
) -> str | None:
    """Return plan code when ``sub`` is entitled, else ``None``."""
    now_dt = now or datetime.now(timezone.utc)
    if sub.status == SubscriptionStatus.paused:
        return None
    if not _within_period(sub, now=now_dt):
        return None
    plan_config_code = await reverse_lookup_code(session, sub.stripe_price_id)
    return resolve_plan_code_for_subscription(sub, plan_config_code=plan_config_code)


__all__ = [
    "resolve_plan_code_for_subscription_row",
    "resolve_plan_code_for_user",
]
