"""Quota routing — free / subscribed / suspended each take the right branch.

Asserts the routing tree from SYSTEM_DESIGN_PHASE_2 §18.3 directly via
:func:`check_and_increment_quota`:

1. **Suspended user** — any action raises :class:`AccountSuspendedError`
   regardless of credits or subscription state.
2. **Free user with credits** — a free-tier-eligible action consumes
   one credit and returns ``charged_to='free_credit'``.  Subscription-
   only actions raise :class:`SubscriptionRequiredError`.
3. **Subscribed user** — increments the right period counter on the
   :class:`Subscription` row and returns ``charged_to='subscription_*'``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditKind,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.credits import get_balance, grant_credit
from app.services.billing.exceptions import (
    AccountSuspendedError,
    SubscriptionRequiredError,
)
from app.services.billing.quota import (
    QuotaAction,
    check_and_increment_quota,
)

pytestmark = pytest.mark.integration


async def _seed_user(
    db_session: AsyncSession,
    *,
    email: str,
    suspended: bool = False,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=email.split("@", 1)[0],
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    if suspended:
        user.suspended_at = datetime.now(timezone.utc)
        user.suspension_reason = "test"
    db_session.add(user)
    await db_session.commit()
    return user


async def _grant_free_credits(
    db_session: AsyncSession, *, user: User, amount: int
) -> None:
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.free,
        delta=amount,
        reason="registration_grant",
    )
    await db_session.commit()


async def _seed_active_subscription(
    db_session: AsyncSession, *, user: User
) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        cancel_at_period_end=False,
        stripe_customer_id="cus_quota_test",
        stripe_subscription_id=f"sub_quota_{uuid.uuid4().hex[:8]}",
        stripe_price_id="price_monthly_test",
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


async def test_suspended_user_blocked_regardless_of_credits(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(
        db_session, email="suspended@example.com", suspended=True
    )
    # Even with credits, suspension wins.
    await _grant_free_credits(db_session, user=user, amount=6)

    with pytest.raises(AccountSuspendedError):
        await check_and_increment_quota(
            db_session, user=user, action=QuotaAction.resume_build
        )


async def test_free_user_resume_build_consumes_credit(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="free@example.com")
    await _grant_free_credits(db_session, user=user, amount=2)

    decision = await check_and_increment_quota(
        db_session, user=user, action=QuotaAction.resume_build
    )
    await db_session.commit()
    assert decision.charged_to == "free_credit"
    assert decision.credit_transaction_id is not None
    balance = await get_balance(
        db_session, user_id=user.id, credit_kind=CreditKind.free
    )
    assert balance == 1


async def test_free_user_blocked_from_subscription_only_action(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="free2@example.com")
    await _grant_free_credits(db_session, user=user, amount=10)

    with pytest.raises(SubscriptionRequiredError):
        await check_and_increment_quota(
            db_session, user=user, action=QuotaAction.job_search
        )


async def test_subscribed_user_increments_period_counters(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="paid@example.com")
    sub = await _seed_active_subscription(db_session, user=user)

    decision = await check_and_increment_quota(
        db_session, user=user, action=QuotaAction.resume_build
    )
    await db_session.commit()
    await db_session.refresh(sub)
    assert decision.charged_to == "subscription_resume"
    assert decision.subscription_id == sub.id
    assert sub.resumes_used == 1

    decision_search = await check_and_increment_quota(
        db_session, user=user, action=QuotaAction.job_search
    )
    await db_session.commit()
    await db_session.refresh(sub)
    assert decision_search.charged_to == "subscription_search"
    assert sub.searches_used == 1
