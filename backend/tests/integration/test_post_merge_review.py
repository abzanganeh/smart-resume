"""Integration tests for post-merge review fixes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.billing import (
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.llm_upgrade import apply_phase3_tier
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.tier_llm import resolve_phase3_model_for_user

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_tier_override_grant_takes_precedence(db_session) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"grant-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Grant User",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        AdminUserGrant(
            user_id=user.id,
            grant_type=AdminGrantType.tier_override,
            payload={"plan_code": "monthly_premium"},
        )
    )
    await db_session.flush()

    plan_code = await resolve_plan_code_for_user(db_session, user)
    assert plan_code == "monthly_premium"


@pytest.mark.asyncio
async def test_expired_subscription_resolves_to_free(db_session) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"expired-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Expired",
        tier=UserTier.pro,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        Subscription(
            id=uuid.uuid4(),
            user_id=user.id,
            plan=SubscriptionPlan.monthly,
            billing_cycle=SubscriptionBillingCycle.recurring,
            status=SubscriptionStatus.active,
            period_start=now - timedelta(days=60),
            period_end=now - timedelta(days=30),
            cancel_at_period_end=False,
            stripe_customer_id="cus",
            stripe_subscription_id="sub",
            stripe_price_id="price_monthly_pro",
            resumes_used=0,
        )
    )
    await db_session.flush()

    plan_code = await resolve_plan_code_for_user(db_session, user, now=now)
    assert plan_code == "free"


@pytest.mark.asyncio
async def test_premium_user_gets_tier_llm_model(db_session) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"prem-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Premium",
        tier=UserTier.pro,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        AdminUserGrant(
            user_id=user.id,
            grant_type=AdminGrantType.tier_override,
            payload={"plan_code": "monthly_premium"},
        )
    )
    await db_session.flush()

    provider, model = await resolve_phase3_model_for_user(
        db_session, user_id=user.id
    )
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_apply_phase3_tier_uses_tier_limits_not_legacy_addons(db_session) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"route-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Route",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="best",
    )
    assert decision.effective_tier == "standard"
    assert decision.provider == "gemini"
    assert decision.model_string == "gemini-2.5-flash-lite"
    assert decision.consumed_credit_id is None
