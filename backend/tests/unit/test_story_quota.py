"""Unit tests for story_build quota routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.billing.quota import (
    QuotaAction,
    check_quota_for_story_generate,
    check_quota_for_story_save,
)


@pytest.mark.asyncio
async def test_story_first_generate_is_free():
    """First story generate per account costs 0 credits."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")
    with patch("app.services.billing.quota._active_subscription_for", return_value=None), patch(
        "app.services.billing.quota._user_has_story_quota_event",
        new_callable=AsyncMock,
        return_value=False,
    ), patch("app.services.billing.quota.record_quota_audit") as mock_audit:
        result = await check_quota_for_story_generate(
            mock_db, user=mock_user, whisper_path=False
        )
    assert result.charged_to == "first_story_generate"
    assert result.action == QuotaAction.story_build_generate
    mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_story_regenerate_charges_credit():
    """Second and later generates consume 1 credit."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")
    mock_txn = MagicMock(id="txn-1")
    with patch("app.services.billing.quota._active_subscription_for", return_value=None), patch(
        "app.services.billing.quota._user_has_story_quota_event",
        new_callable=AsyncMock,
        return_value=True,
    ), patch("app.services.billing.quota.consume_credit", return_value=mock_txn) as mock_consume:
        result = await check_quota_for_story_generate(
            mock_db, user=mock_user, whisper_path=False
        )
    assert result.charged_to == "free_credit"
    assert result.action == QuotaAction.story_build_generate
    mock_consume.assert_called_once()


@pytest.mark.asyncio
async def test_story_first_save_is_free():
    """First save to profile per account costs 0 credits."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")
    with patch("app.services.billing.quota._active_subscription_for", return_value=None), patch(
        "app.services.billing.quota._user_has_story_quota_event",
        new_callable=AsyncMock,
        return_value=False,
    ), patch("app.services.billing.quota.record_quota_audit") as mock_audit:
        result = await check_quota_for_story_save(mock_db, user=mock_user)
    assert result.charged_to == "first_story_save"
    assert result.action == QuotaAction.story_build_save
    mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_story_whisper_blocked_for_free_tier() -> None:
    """Free tier cannot use Whisper path."""
    from app.services.billing.exceptions import WhisperNotAllowedError
    from app.services.billing.whisper_gate import check_and_increment_whisper_use

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")

    with patch(
        "app.services.billing.whisper_gate._resolve_limits_for_user",
        new_callable=AsyncMock,
        return_value=(
            __import__(
                "app.services.billing.tier_limits_lookup", fromlist=["TierLimits"]
            ).TierLimits(
                plan_code="free",
                resumes_per_period=3,
                cover_letters_per_period=3,
                searches_per_period=5,
                fit_analyses_per_period=3,
                checkups_per_period=3,
                story_sessions=1,
                coached_sessions=1,
                whisper_enabled=False,
                whisper_uses_per_period=0,
                soft_cap_message=None,
            ),
            None,
            0,
        ),
    ), patch(
        "app.services.billing.whisper_gate.user_has_feature_unlock",
        new_callable=AsyncMock,
        return_value=False,
    ):
        with pytest.raises(WhisperNotAllowedError):
            await check_and_increment_whisper_use(mock_db, user=mock_user)


@pytest.mark.asyncio
async def test_story_subscriber_generate_is_free():
    """Active subscribers pay 0 credits for story generates."""
    from datetime import datetime, timezone, timedelta
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
        result = await check_quota_for_story_generate(
            mock_db, user=mock_user, whisper_path=False
        )
    assert result.charged_to == "subscription"
    assert result.action == QuotaAction.story_build_generate


def test_story_generate_and_save_in_free_credit_actions():
    """story generate/save must be in FREE_CREDIT_ACTIONS."""
    from app.services.billing.quota import FREE_CREDIT_ACTIONS

    assert QuotaAction.story_build_generate in FREE_CREDIT_ACTIONS
    assert QuotaAction.story_build_save in FREE_CREDIT_ACTIONS


@pytest.mark.asyncio
async def test_story_coach_second_segment_same_session_is_free():
    """One credit per story build session — second coach call reuses the charge."""
    from app.services.billing.quota import check_quota_for_story_coach

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")

    with patch(
        "app.services.billing.quota._story_coach_build_already_charged",
        new_callable=AsyncMock,
        return_value=True,
    ), patch("app.services.billing.quota._active_subscription_for", return_value=None), patch(
        "app.services.billing.quota.consume_credit",
    ) as mock_consume:
        result = await check_quota_for_story_coach(
            mock_db,
            user=mock_user,
            session_id="story-build-abc",
        )

    assert result.charged_to == "story_build_session_included"
    mock_consume.assert_not_called()


@pytest.mark.asyncio
async def test_story_coach_first_segment_charges_one_credit():
    """First coach call in a story build session consumes 1 credit."""
    from app.services.billing.quota import check_quota_for_story_coach

    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")
    mock_txn = MagicMock(id="txn-1")

    with patch(
        "app.services.billing.quota._story_coach_build_already_charged",
        new_callable=AsyncMock,
        return_value=False,
    ), patch("app.services.billing.quota._active_subscription_for", return_value=None), patch(
        "app.services.billing.quota.consume_credit",
        return_value=mock_txn,
    ) as mock_consume:
        result = await check_quota_for_story_coach(
            mock_db,
            user=mock_user,
            session_id="story-build-abc",
        )

    assert result.charged_to == "free_credit"
    mock_consume.assert_called_once()
