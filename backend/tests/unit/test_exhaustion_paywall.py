"""Unit tests for contextual exhaustion paywall payload (M21 slice 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import PlanConfig, PlanConfigInterval
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.exhaustion_paywall import (
    EXHAUSTION_PAYWALL_PLAN_CODES,
    FREE_STILL_AVAILABLE,
    _filter_upgrade_plans,
    _yearly_savings_percent,
    build_exhaustion_paywall,
    insufficient_credits_detail,
)
from app.services.billing.exceptions import InsufficientCreditsError
from app.services.billing.exhaustion_top_up import ExhaustionTopUpEligibility

pytestmark = pytest.mark.unit


def _user(*, verified: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email="free@example.com",
        email_canonical="free@example.com",
        display_name="Free User",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        credit_balance=0,
        email_verified_at=datetime.now(timezone.utc) if verified else None,
    )


def test_filter_upgrade_plans_keeps_canonical_order() -> None:
    plans = [
        {"code": "yearly_pro", "amount_cents": 19900},
        {"code": "monthly_plus", "amount_cents": 2999},
        {"code": "weekly", "amount_cents": 499},
        {"code": "monthly_pro", "amount_cents": 1999},
    ]
    filtered = _filter_upgrade_plans(plans)
    assert [plan["code"] for plan in filtered] == list(EXHAUSTION_PAYWALL_PLAN_CODES)


def test_yearly_savings_percent_from_live_amounts() -> None:
    plans = [
        {"code": "monthly_pro", "amount_cents": 2000},
        {"code": "yearly_pro", "amount_cents": 20000},
    ]
    assert _yearly_savings_percent(plans) == 17


@pytest.mark.asyncio
async def test_build_exhaustion_paywall_with_mocks() -> None:
    user = _user()
    mock_session = AsyncMock(spec=AsyncSession)
    public_prices = {
        "currency": "USD",
        "plans": [
            {"code": "weekly", "amount_cents": 499, "display_name": "Weekly"},
            {"code": "monthly_pro", "amount_cents": 1999, "display_name": "Pro"},
            {"code": "yearly_pro", "amount_cents": 19900, "display_name": "Pro"},
            {"code": "monthly_plus", "amount_cents": 2999, "display_name": "Pro+"},
        ],
    }
    with (
        patch(
            "app.services.billing.exhaustion_paywall.build_public_billing_prices",
            new=AsyncMock(return_value=public_prices),
        ),
        patch(
            "app.services.billing.exhaustion_paywall.get_balance",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.services.billing.exhaustion_paywall.get_exhaustion_top_up_eligibility",
            new=AsyncMock(
                return_value=ExhaustionTopUpEligibility(True, 3),
            ),
        ),
    ):
        payload = await build_exhaustion_paywall(mock_session, user=user)

    assert payload["headline"]
    assert payload["credit_balance"] == 0
    assert [item["id"] for item in payload["free_still_available"]] == [
        item["id"] for item in FREE_STILL_AVAILABLE
    ]
    assert [plan["code"] for plan in payload["upgrade_plans"]] == list(
        EXHAUSTION_PAYWALL_PLAN_CODES
    )
    assert payload["exhaustion_top_up_eligible"] is True
    assert payload["highlight_plan_code"] == "monthly_pro"


@pytest.mark.asyncio
async def test_insufficient_credits_detail_embeds_paywall() -> None:
    user = _user()
    mock_session = AsyncMock(spec=AsyncSession)
    with patch(
        "app.services.billing.exhaustion_paywall.build_exhaustion_paywall",
        new=AsyncMock(return_value={"upgrade_plans": [{"code": "monthly_pro"}]}),
    ):
        exc = InsufficientCreditsError("free", 0)
        detail = await insufficient_credits_detail(
            mock_session,
            user=user,
            exc=exc,
            message="Test message",
            action="cover_letter",
        )

    assert detail["code"] == "insufficient_credits"
    assert detail["message"] == "Test message"
    assert detail["action"] == "cover_letter"
    assert detail["balance"] == 0
    assert detail["paywall"]["upgrade_plans"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_build_exhaustion_paywall_integration(db_session: AsyncSession) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()

    for code, amount, interval in (
        ("weekly", 499, PlanConfigInterval.week),
        ("monthly_pro", 1999, PlanConfigInterval.month),
        ("yearly_pro", 19900, PlanConfigInterval.year),
        ("monthly_plus", 2999, PlanConfigInterval.month),
    ):
        db_session.add(
            PlanConfig(
                id=uuid.uuid4(),
                code=code,
                stripe_price_id=f"price_{code}_test",
                amount_cents=amount,
                interval=interval,
                is_active=True,
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                effective_to=None,
            )
        )
    await db_session.flush()

    payload = await build_exhaustion_paywall(db_session, user=user)
    assert [plan["code"] for plan in payload["upgrade_plans"]] == list(
        EXHAUSTION_PAYWALL_PLAN_CODES
    )
