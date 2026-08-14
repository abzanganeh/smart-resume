"""Unit tests for quota routing against TierLimitsConfig (slice 4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.billing import (
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.services.billing.plan_code import resolve_plan_code_for_subscription
from app.services.billing.quota import (
    QuotaAction,
    check_and_increment_quota,
    check_quota_for_story,
    check_quota_for_story_coach,
)
from app.services.billing.tier_limits_lookup import (
    TierLimits,
    get_active_tier_limits,
    registration_grant_credits,
)


@pytest.mark.asyncio
async def test_get_active_tier_limits_falls_back_to_seed() -> None:
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    limits = await get_active_tier_limits(mock_session, "monthly_pro")
    assert limits.plan_code == "monthly_pro"
    assert limits.resumes_per_period == 50
    assert limits.searches_per_period == 100


def test_registration_grant_matches_free_tier_resumes() -> None:
    assert registration_grant_credits() == 3


def test_resolve_plan_code_legacy_monthly_recurring() -> None:
    sub = MagicMock(
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_unknown",
    )
    assert resolve_plan_code_for_subscription(sub, plan_config_code=None) == "monthly_pro"


def test_resolve_plan_code_from_plan_config_code() -> None:
    sub = MagicMock(
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        stripe_price_id="price_pro",
    )
    assert (
        resolve_plan_code_for_subscription(sub, plan_config_code="monthly_pro")
        == "monthly_pro"
    )


@pytest.mark.asyncio
async def test_subscriber_search_limit_from_tier_limits() -> None:
    """Subscriber at search limit raises PlanLimitReachedError."""
    from app.services.billing.exceptions import PlanLimitReachedError

    now = datetime.now(timezone.utc)
    mock_sub = MagicMock()
    mock_sub.id = uuid4()
    mock_sub.status = SubscriptionStatus.active
    mock_sub.period_start = now - timedelta(days=1)
    mock_sub.period_end = now + timedelta(days=29)
    mock_sub.plan = SubscriptionPlan.monthly
    mock_sub.billing_cycle = SubscriptionBillingCycle.recurring
    mock_sub.stripe_price_id = "price_pro"
    mock_sub.resumes_used = 0
    mock_sub.searches_used = 100

    mock_user = MagicMock(is_suspended=False, id=uuid4())
    mock_db = AsyncMock()

    limits = TierLimits(
        plan_code="monthly_pro",
        resumes_per_period=50,
        cover_letters_per_period=50,
        searches_per_period=100,
        fit_analyses_per_period=50,
        checkups_per_period=None,
        story_sessions=None,
        coached_sessions=None,
        whisper_enabled=True,
        whisper_uses_per_period=5,
        soft_cap_message=None,
    )

    with patch(
        "app.services.billing.quota._active_subscription_for",
        return_value=mock_sub,
    ), patch(
        "app.services.billing.quota._tier_limits_for_subscription",
        new_callable=AsyncMock,
        return_value=limits,
    ):
        with pytest.raises(PlanLimitReachedError):
            await check_and_increment_quota(
                mock_db, user=mock_user, action=QuotaAction.job_search
            )


@pytest.mark.asyncio
async def test_story_byok_path_removed_whisper_gated() -> None:
    """Whisper path invokes tier gate before story quota."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())
    mock_txn = MagicMock(id=uuid4())

    with patch(
        "app.services.billing.whisper_gate.check_and_increment_whisper_use",
        new_callable=AsyncMock,
    ) as mock_whisper, patch(
        "app.services.billing.quota._active_subscription_for",
        return_value=None,
    ), patch(
        "app.services.billing.quota.consume_credit",
        return_value=mock_txn,
    ):
        result = await check_quota_for_story(
            mock_db,
            user=mock_user,
            whisper_path=True,
        )

    mock_whisper.assert_awaited_once()
    assert result.charged_to == "free_credit"


@pytest.mark.asyncio
async def test_story_coach_no_byok_param() -> None:
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())
    mock_txn = MagicMock(id=uuid4())

    with patch(
        "app.services.billing.quota._story_coach_build_already_charged",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "app.services.billing.quota._active_subscription_for",
        return_value=None,
    ), patch(
        "app.services.billing.quota.consume_credit",
        return_value=mock_txn,
    ):
        result = await check_quota_for_story_coach(
            mock_db,
            user=mock_user,
            session_id="story-1",
        )

    assert result.charged_to == "free_credit"
