"""Regression: UI must not advertise a trial Stripe checkout never configures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import PlanConfig, PlanConfigInterval
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.public_prices import build_public_billing_prices
from app.services.billing.subscription import create_checkout_session

pytestmark = pytest.mark.unit


async def _seed_monthly_plan(db_session: AsyncSession) -> PlanConfig:
    plan = PlanConfig(
        id=uuid.uuid4(),
        code="monthly_pro",
        stripe_price_id="price_monthly_pro_test",
        amount_cents=1999,
        interval=PlanConfigInterval.month,
        is_active=True,
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_prices_never_advertise_trial(db_session: AsyncSession) -> None:
    await _seed_monthly_plan(db_session)
    payload = await build_public_billing_prices(db_session)
    for plan in payload["plans"]:
        assert plan["trial_days"] is None


@pytest.mark.asyncio
async def test_checkout_session_omits_trial_period_days() -> None:
    user = User(
        id=uuid.uuid4(),
        email="checkout-no-trial@example.com",
        display_name="Checkout",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        credit_balance=0,
    )

    captured: dict[str, Any] = {}

    def _fake_create(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"id": "cs_test", "url": "https://checkout.stripe.test/session"}

    mock_session = AsyncMock()
    with (
        patch(
            "app.services.billing.subscription.resolve_price_id",
            new=AsyncMock(return_value="price_monthly_pro_test"),
        ),
        patch(
            "app.services.billing.subscription.stripe.checkout.Session.create",
            side_effect=_fake_create,
        ),
    ):
        await create_checkout_session(
            mock_session,
            user=user,
            code="monthly_pro",
            success_url="http://localhost:3100/success",
            cancel_url="http://localhost:3100/cancel",
        )

    sub_data = captured.get("subscription_data") or {}
    assert "trial_period_days" not in sub_data
    assert sub_data.get("metadata") is not None
