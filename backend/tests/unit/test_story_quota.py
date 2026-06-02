"""Unit tests for story_build quota routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.billing.quota import check_quota_for_story, QuotaAction


@pytest.mark.asyncio
async def test_story_byok_is_free():
    """BYOK users pay 0 credits regardless of browser path."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False)
    result = await check_quota_for_story(
        mock_db, user=mock_user, whisper_path=True, byok_active=True
    )
    assert result.charged_to == "byok"
    assert result.action == QuotaAction.story_build


@pytest.mark.asyncio
async def test_story_web_speech_is_free():
    """Web Speech path costs 0 credits for free users (no subscription)."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False)
    with patch("app.services.billing.quota._active_subscription_for", return_value=None):
        result = await check_quota_for_story(
            mock_db, user=mock_user, whisper_path=False, byok_active=False
        )
    assert result.charged_to == "free_web_speech"
    assert result.action == QuotaAction.story_build


@pytest.mark.asyncio
async def test_story_whisper_costs_two_credits():
    """Whisper path costs 2 credits for free users."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")
    mock_transaction = MagicMock(id="txn-1")
    with patch("app.services.billing.quota._active_subscription_for", return_value=None), \
         patch("app.services.billing.quota.consume_credit", return_value=mock_transaction) as mock_consume:
        result = await check_quota_for_story(
            mock_db, user=mock_user, whisper_path=True, byok_active=False
        )
    assert result.charged_to == "free_credit"
    # consume_credit called twice (2 credits)
    assert mock_consume.call_count == 2


@pytest.mark.asyncio
async def test_story_subscriber_is_free():
    """Active subscribers pay 0 credits for story builds."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import MagicMock
    from app.models.billing import SubscriptionStatus

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")

    now = datetime.now(timezone.utc)
    mock_sub = MagicMock()
    mock_sub.id = "sub-1"
    mock_sub.status = SubscriptionStatus.active
    mock_sub.period_start = now - timedelta(days=1)
    mock_sub.period_end = now + timedelta(days=29)

    with patch("app.services.billing.quota._active_subscription_for", return_value=mock_sub):
        result = await check_quota_for_story(
            mock_db, user=mock_user, whisper_path=True, byok_active=False
        )
    assert result.charged_to == "subscription"
    assert result.action == QuotaAction.story_build


def test_story_build_in_free_credit_actions():
    """story_build must be in FREE_CREDIT_ACTIONS."""
    from app.services.billing.quota import FREE_CREDIT_ACTIONS
    assert QuotaAction.story_build in FREE_CREDIT_ACTIONS
