"""Grace tick — stale ``grace`` rows transition to ``expired`` exactly once.

Asserts the contract from IMPLEMENTATION_PLAN §7.6:

1. Subscription in ``grace`` with ``payment_failed_at`` older than the
   72-hour cutoff transitions to ``expired`` and gets ``ended_at`` set.
2. Re-running the tick is a no-op (the WHERE clause excludes already
   expired rows).
3. Subscriptions whose ``payment_failed_at`` is *inside* the window
   (e.g. < 72h ago) are left untouched.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.grace_tick import run_grace_tick

pytestmark = pytest.mark.integration


async def _seed_user(db_session: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=email.split("@", 1)[0],
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _seed_grace_subscription(
    db_session: AsyncSession,
    *,
    user: User,
    payment_failed_at: datetime,
    stripe_id: str,
) -> Subscription:
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.grace,
        period_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        cancel_at_period_end=False,
        payment_failed_at=payment_failed_at,
        stripe_customer_id="cus_grace",
        stripe_subscription_id=stripe_id,
        stripe_price_id="price_monthly_test",
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


async def test_grace_tick_expires_stale_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(hours=settings.SUBSCRIPTION_GRACE_HOURS)

    stale_user = await _seed_user(db_session, "stale@example.com")
    fresh_user = await _seed_user(db_session, "fresh@example.com")

    stale = await _seed_grace_subscription(
        db_session,
        user=stale_user,
        payment_failed_at=cutoff - timedelta(hours=1),  # past the cutoff
        stripe_id="sub_grace_stale",
    )
    fresh = await _seed_grace_subscription(
        db_session,
        user=fresh_user,
        payment_failed_at=cutoff + timedelta(hours=1),  # still inside window
        stripe_id="sub_grace_fresh",
    )

    result = await run_grace_tick(db_session, now=now)
    await db_session.commit()
    await db_session.refresh(stale)
    await db_session.refresh(fresh)

    assert stale.id in result.expired
    assert fresh.id not in result.expired
    assert stale.status == SubscriptionStatus.expired
    assert stale.ended_at == now
    assert fresh.status == SubscriptionStatus.grace

    # Re-running the tick is idempotent: nothing left to expire.
    result2 = await run_grace_tick(db_session, now=now)
    await db_session.commit()
    assert result2.expired == []
    await db_session.refresh(stale)
    assert stale.status == SubscriptionStatus.expired
    # ended_at should not have shifted on the no-op re-run.
    assert stale.ended_at == now
