"""Subscriber migration for pricing restructure (slice 10)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditKind,
    LLMUpgradeBillingCycle,
    LLMUpgradeTier,
    PlanConfig,
    PlanConfigInterval,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import AuthProvider, CreditTransaction, CreditTransactionAction, User, UserTier
from app.services.billing.credits import get_balance
from app.services.billing.subscriber_migration import (
    is_addon_subscription,
    run_subscriber_migration,
    target_plan_config_code,
)

pytestmark = pytest.mark.integration


def test_target_plan_config_code_daily_to_weekly() -> None:
    sub = Subscription(
        plan=SubscriptionPlan.daily,
        billing_cycle=SubscriptionBillingCycle.recurring,
        llm_upgrade=LLMUpgradeTier.standard,
    )
    assert target_plan_config_code(sub) == "weekly"


def test_target_plan_config_code_monthly_recurring_to_pro() -> None:
    sub = Subscription(
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        llm_upgrade=LLMUpgradeTier.standard,
    )
    assert target_plan_config_code(sub) == "monthly_pro"


def test_target_plan_config_code_monthly_yearly_to_pro() -> None:
    sub = Subscription(
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.yearly,
        llm_upgrade=LLMUpgradeTier.standard,
    )
    assert target_plan_config_code(sub) == "yearly_pro"


def test_target_plan_config_code_returns_none_for_addon() -> None:
    sub = Subscription(
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        llm_upgrade=LLMUpgradeTier.better,
    )
    assert target_plan_config_code(sub) is None


def test_is_addon_subscription() -> None:
    base = Subscription(llm_upgrade=LLMUpgradeTier.standard)
    addon = Subscription(llm_upgrade=LLMUpgradeTier.best)
    assert is_addon_subscription(base) is False
    assert is_addon_subscription(addon) is True


async def _seed_user(db: AsyncSession, email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email or f"migrate-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Migrate User",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_plan_configs(db: AsyncSession) -> None:
    for code, price_id, interval in (
        ("weekly", "price_weekly_new", PlanConfigInterval.week),
        ("monthly_pro", "price_monthly_pro_new", PlanConfigInterval.month),
        ("yearly_pro", "price_yearly_pro_new", PlanConfigInterval.year),
    ):
        db.add(
            PlanConfig(
                id=uuid.uuid4(),
                code=code,
                stripe_price_id=price_id,
                stripe_product_id=f"prod_{code}",
                eligibility="base_plan",
                amount_cents=999,
                currency="USD",
                interval=interval,
                is_active=True,
            )
        )
    await db.flush()


async def _seed_subscription(
    db: AsyncSession,
    *,
    user: User,
    plan: SubscriptionPlan,
    billing_cycle: SubscriptionBillingCycle,
    stripe_price_id: str,
    llm_upgrade: LLMUpgradeTier = LLMUpgradeTier.standard,
    llm_upgrade_billing_cycle: LLMUpgradeBillingCycle | None = None,
) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=plan,
        billing_cycle=billing_cycle,
        llm_upgrade=llm_upgrade,
        llm_upgrade_billing_cycle=llm_upgrade_billing_cycle,
        status=SubscriptionStatus.active,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:10]}",
        stripe_subscription_id=f"sub_{uuid.uuid4().hex[:10]}",
        stripe_price_id=stripe_price_id,
    )
    db.add(sub)
    await db.flush()
    return sub


@pytest.mark.asyncio
async def test_migrate_daily_subscription_to_weekly(db_session: AsyncSession) -> None:
    await _seed_plan_configs(db_session)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.daily,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_daily_legacy",
    )

    stats = await run_subscriber_migration(db_session, dry_run=False)

    await db_session.refresh(sub)
    assert stats.daily_to_weekly == 1
    assert stats.base_plans_updated == 1
    assert sub.plan == SubscriptionPlan.weekly
    assert sub.stripe_price_id == "price_weekly_new"


@pytest.mark.asyncio
async def test_migrate_monthly_recurring_to_monthly_pro(db_session: AsyncSession) -> None:
    await _seed_plan_configs(db_session)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_monthly_legacy",
    )

    stats = await run_subscriber_migration(db_session, dry_run=False)

    await db_session.refresh(sub)
    assert stats.monthly_to_pro == 1
    assert stats.base_plans_updated == 1
    assert sub.plan == SubscriptionPlan.monthly
    assert sub.stripe_price_id == "price_monthly_pro_new"


@pytest.mark.asyncio
async def test_migrate_expires_addon_subscription_and_credits(
    db_session: AsyncSession,
) -> None:
    await _seed_plan_configs(db_session)
    user = await _seed_user(db_session)
    base = await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_monthly_legacy",
    )
    addon = await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_better_monthly_legacy",
        llm_upgrade=LLMUpgradeTier.better,
        llm_upgrade_billing_cycle=LLMUpgradeBillingCycle.monthly,
    )
    db_session.add(
        CreditTransaction(
            id=uuid.uuid4(),
            user_id=user.id,
            delta=3,
            action=CreditTransactionAction.llm_upgrade_pack,
            reason="purchase_better_pack",
            credit_kind=CreditKind.better,
        )
    )
    await db_session.flush()

    stats = await run_subscriber_migration(db_session, dry_run=False)

    await db_session.refresh(base)
    await db_session.refresh(addon)
    assert stats.addons_expired == 1
    assert stats.credits_expired == 1
    assert addon.status == SubscriptionStatus.expired
    assert addon.ended_at is not None
    assert addon.llm_upgrade == LLMUpgradeTier.standard
    assert addon.llm_upgrade_billing_cycle is None
    assert await get_balance(db_session, user_id=user.id, credit_kind=CreditKind.better) == 0
    assert base.status == SubscriptionStatus.active


@pytest.mark.asyncio
async def test_migrate_dry_run_does_not_mutate(db_session: AsyncSession) -> None:
    await _seed_plan_configs(db_session)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.daily,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_daily_legacy",
    )
    original_plan = sub.plan
    original_price = sub.stripe_price_id

    stats = await run_subscriber_migration(db_session, dry_run=True)

    await db_session.refresh(sub)
    assert stats.daily_to_weekly == 1
    assert sub.plan == original_plan
    assert sub.stripe_price_id == original_price


@pytest.mark.asyncio
async def test_migrate_sync_stripe_calls_modify(db_session: AsyncSession) -> None:
    await _seed_plan_configs(db_session)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.daily,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_daily_legacy",
    )

    mock_modify = AsyncMock(
        return_value={
            "id": sub.stripe_subscription_id,
            "items": {"data": [{"id": "si_test", "price": {"id": "price_weekly_new"}}]},
        }
    )
    mock_retrieve = AsyncMock(
        return_value={
            "id": sub.stripe_subscription_id,
            "items": {"data": [{"id": "si_test", "price": {"id": "price_daily_legacy"}}]},
        }
    )

    with patch(
        "app.services.billing.subscriber_migration._stripe_subscription_modify",
        new=mock_modify,
    ), patch(
        "app.services.billing.subscriber_migration._stripe_subscription_retrieve",
        new=mock_retrieve,
    ):
        stats = await run_subscriber_migration(
            db_session, dry_run=False, sync_stripe=True
        )

    assert stats.base_plans_updated == 1
    mock_retrieve.assert_awaited_once()
    mock_modify.assert_awaited_once()
