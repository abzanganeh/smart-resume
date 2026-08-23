"""Phase 3 routing uses tier_limits_config LLM (post-merge review)."""

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

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_phase3_routes_premium_tier_to_claude(db_session) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"prem-route-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Premium Route",
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
            period_start=now - timedelta(days=1),
            period_end=now + timedelta(days=29),
            cancel_at_period_end=False,
            stripe_customer_id="cus",
            stripe_subscription_id="sub",
            stripe_price_id="price_unknown",
            resumes_used=0,
        )
    )
    db_session.add(
        AdminUserGrant(
            user_id=user.id,
            grant_type=AdminGrantType.tier_override,
            payload={"plan_code": "monthly_premium"},
        )
    )
    await db_session.commit()

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="best",
    )
    assert decision.provider == "gemini"
    assert decision.model_string == "gemini-2.5-flash"
    assert decision.consumed_credit_id is None
