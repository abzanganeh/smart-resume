"""Unit tests for ``app.services.billing.llm_upgrade.get_user_phase3_tier``.

Asserts the four canonical cases from the user-prompt for Step 19:

1. ``standard`` when no LLM upgrade is active.
2. ``better`` when an active Better add-on subscription is in period.
3. ``better`` when only Better credit balance > 0 (no add-on subscription).
4. ``best`` when an active Best subscription is below the soft cap.
5. ``standard`` (with ``best_soft_cap_hit`` flag) once
   ``upgraded_resumes_used >= 100``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditKind,
    LLMUpgradeBillingCycle,
    LLMUpgradeTier,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.credits import grant_credit
from app.services.billing.llm_upgrade import (
    BEST_SUBSCRIPTION_SOFT_CAP,
    get_phase3_tier_status,
    get_user_phase3_tier,
)

pytestmark = pytest.mark.integration


async def _seed_user(db_session: AsyncSession, *, email: str) -> User:
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
    await db_session.commit()
    return user


async def _seed_addon_subscription(
    db_session: AsyncSession,
    *,
    user: User,
    tier: LLMUpgradeTier,
    addon_billing: LLMUpgradeBillingCycle = LLMUpgradeBillingCycle.monthly,
    upgraded_used: int = 0,
    base_cycle: SubscriptionBillingCycle = SubscriptionBillingCycle.recurring,
) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=base_cycle,
        llm_upgrade=tier,
        llm_upgrade_billing_cycle=addon_billing,
        status=SubscriptionStatus.active,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        upgraded_resumes_used=upgraded_used,
        cancel_at_period_end=False,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
        stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
        stripe_price_id=f"price_{tier.value}_test",
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


async def test_user_with_no_upgrade_returns_standard(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="standard@example.com")

    tier = await get_user_phase3_tier(db_session, user_id=user.id)
    assert tier == "standard"

    status = await get_phase3_tier_status(db_session, user_id=user.id)
    assert status.entitled_tier == "standard"
    assert status.better_subscription_active is False
    assert status.best_subscription_active is False
    assert status.better_credits_balance == 0
    assert status.best_soft_cap_hit is False


async def test_user_with_better_subscription_returns_better(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="better-sub@example.com")
    await _seed_addon_subscription(
        db_session, user=user, tier=LLMUpgradeTier.better
    )

    tier = await get_user_phase3_tier(db_session, user_id=user.id)
    assert tier == "better"


async def test_user_with_better_credit_balance_returns_better(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="better-credit@example.com")
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.better,
        delta=5,
        reason="purchase_better_5pack",
    )
    await db_session.commit()

    tier = await get_user_phase3_tier(db_session, user_id=user.id)
    assert tier == "better"

    status = await get_phase3_tier_status(db_session, user_id=user.id)
    assert status.better_credits_balance == 5
    assert status.better_subscription_active is False


async def test_user_with_best_subscription_below_cap_returns_best(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="best@example.com")
    await _seed_addon_subscription(
        db_session,
        user=user,
        tier=LLMUpgradeTier.best,
        upgraded_used=BEST_SUBSCRIPTION_SOFT_CAP - 1,
    )

    tier = await get_user_phase3_tier(db_session, user_id=user.id)
    assert tier == "best"


async def test_user_with_best_subscription_at_cap_returns_standard(
    db_session: AsyncSession,
) -> None:
    """User-prompt acceptance: returns "standard" when upgraded_resumes_used=100."""
    user = await _seed_user(db_session, email="best-capped@example.com")
    await _seed_addon_subscription(
        db_session,
        user=user,
        tier=LLMUpgradeTier.best,
        upgraded_used=BEST_SUBSCRIPTION_SOFT_CAP,
    )

    tier = await get_user_phase3_tier(db_session, user_id=user.id)
    assert tier == "standard", "Best soft cap should fall back to standard"

    status = await get_phase3_tier_status(db_session, user_id=user.id)
    assert status.best_soft_cap_hit is True
    assert status.upgraded_resumes_used == BEST_SUBSCRIPTION_SOFT_CAP


async def test_yearly_base_cycle_is_reported(
    db_session: AsyncSession,
) -> None:
    """Status surface exposes base billing cycle so the UI can gate
    yearly add-on options (§7.7).
    """
    user = await _seed_user(db_session, email="yearly-base@example.com")
    await _seed_addon_subscription(
        db_session,
        user=user,
        tier=LLMUpgradeTier.standard,
        base_cycle=SubscriptionBillingCycle.yearly,
    )

    status = await get_phase3_tier_status(db_session, user_id=user.id)
    assert status.base_billing_cycle == "yearly"
