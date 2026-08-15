"""Unit tests for tier-based Whisper gating (slice 6)."""

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
from app.services.billing.exceptions import PlanLimitReachedError, WhisperNotAllowedError
from app.services.billing.tier_limits_lookup import TierLimits
from app.services.billing.whisper_gate import (
    check_and_increment_whisper_use,
    whisper_entitlement_for_user,
)


def _limits(
    *,
    plan_code: str = "free",
    enabled: bool = False,
    uses: int | None = 0,
) -> TierLimits:
    return TierLimits(
        plan_code=plan_code,
        resumes_per_period=3,
        cover_letters_per_period=3,
        searches_per_period=5,
        fit_analyses_per_period=3,
        checkups_per_period=3,
        story_sessions=1,
        coached_sessions=1,
        whisper_enabled=enabled,
        whisper_uses_per_period=uses,
        soft_cap_message=None,
    )


def _patch_whisper_unlock(*, unlocked: bool = False):
    return patch(
        "app.services.billing.whisper_gate.user_has_feature_unlock",
        new_callable=AsyncMock,
        return_value=unlocked,
    )


@pytest.mark.asyncio
async def test_free_tier_whisper_not_allowed() -> None:
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(_limits(enabled=False), None, 0),
    ), _patch_whisper_unlock():
        with pytest.raises(WhisperNotAllowedError):
            await check_and_increment_whisper_use(mock_db, user=mock_user)


@pytest.mark.asyncio
async def test_weekly_tier_increments_whisper_counter() -> None:
    now = datetime.now(timezone.utc)
    mock_sub = MagicMock()
    mock_sub.id = uuid4()
    mock_sub.status = SubscriptionStatus.active
    mock_sub.period_start = now - timedelta(days=1)
    mock_sub.period_end = now + timedelta(days=6)
    mock_sub.whisper_uses_used = 0

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(_limits(plan_code="weekly", enabled=True, uses=2), mock_sub, 0),
    ), _patch_whisper_unlock():
        decision = await check_and_increment_whisper_use(mock_db, user=mock_user)

    assert decision.charged_to == "subscription_whisper"
    assert mock_sub.whisper_uses_used == 1


@pytest.mark.asyncio
async def test_whisper_limit_reached_raises() -> None:
    now = datetime.now(timezone.utc)
    mock_sub = MagicMock()
    mock_sub.id = uuid4()
    mock_sub.status = SubscriptionStatus.active
    mock_sub.period_start = now - timedelta(days=1)
    mock_sub.period_end = now + timedelta(days=6)
    mock_sub.whisper_uses_used = 2

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(_limits(plan_code="weekly", enabled=True, uses=2), mock_sub, 2),
    ), _patch_whisper_unlock():
        with pytest.raises(PlanLimitReachedError):
            await check_and_increment_whisper_use(mock_db, user=mock_user)


@pytest.mark.asyncio
async def test_whisper_unlock_bypasses_free_tier_gate() -> None:
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(_limits(enabled=False), None, 0),
    ), _patch_whisper_unlock(unlocked=True):
        decision = await check_and_increment_whisper_use(mock_db, user=mock_user)

    assert decision.charged_to == "feature_unlock_whisper"


@pytest.mark.asyncio
async def test_entitlement_enabled_when_whisper_unlocked() -> None:
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(_limits(enabled=False), None, 0),
    ), _patch_whisper_unlock(unlocked=True):
        ent = await whisper_entitlement_for_user(mock_db, user=mock_user)

    assert ent.enabled is True
    assert ent.limit is None
    assert ent.remaining is None


@pytest.mark.asyncio
async def test_entitlement_reports_remaining_uses() -> None:
    now = datetime.now(timezone.utc)
    mock_sub = MagicMock()
    mock_sub.whisper_uses_used = 2
    mock_sub.status = SubscriptionStatus.active
    mock_sub.period_start = now - timedelta(days=1)
    mock_sub.period_end = now + timedelta(days=29)

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id=uuid4())

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(
            _limits(plan_code="monthly_pro", enabled=True, uses=5),
            mock_sub,
            2,
        ),
    ), _patch_whisper_unlock():
        ent = await whisper_entitlement_for_user(mock_db, user=mock_user)

    assert ent.enabled is True
    assert ent.limit == 5
    assert ent.used == 2
    assert ent.remaining == 3
