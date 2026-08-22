"""Unit tests for free-credit pack registry (M21 slice 5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import CreditKind, PlanConfig, PlanConfigInterval
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.credit_packs import (
    CREDIT_PACK_CODES,
    grant_for_one_time_code,
    is_credit_pack_code,
    is_one_time_purchase_code,
)
from app.services.billing.public_prices import build_public_billing_prices
from app.services.billing.subscription import create_checkout_session

pytestmark = pytest.mark.unit


def test_credit_pack_codes_and_grants() -> None:
    assert is_credit_pack_code("credits_5")
    assert is_credit_pack_code("credits_15")
    assert not is_credit_pack_code("better_pack")
    assert is_one_time_purchase_code("credits_5")
    assert is_one_time_purchase_code("better_pack")
    assert grant_for_one_time_code("credits_5") == (CreditKind.free, 5)
    assert grant_for_one_time_code("credits_15") == (CreditKind.free, 15)
    assert grant_for_one_time_code("better_pack") == (CreditKind.better, 5)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_build_public_billing_prices_includes_credit_pack_addons(
    db_session: AsyncSession,
) -> None:
    now = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for code, amount in (("credits_5", 500), ("credits_15", 1200)):
        db_session.add(
            PlanConfig(
                id=uuid.uuid4(),
                code=code,
                stripe_price_id=f"price_{code}_test",
                amount_cents=amount,
                interval=PlanConfigInterval.one_time,
                eligibility="credit_pack",
                is_active=True,
                effective_from=now,
            )
        )
    db_session.add(
        PlanConfig(
            id=uuid.uuid4(),
            code="monthly_pro",
            stripe_price_id="price_monthly_pro_test",
            amount_cents=1999,
            interval=PlanConfigInterval.month,
            eligibility="base_plan",
            is_active=True,
            effective_from=now,
        )
    )
    await db_session.flush()

    payload = await build_public_billing_prices(db_session)
    addon_codes = [addon["code"] for addon in payload["addons"]]
    assert addon_codes == list(CREDIT_PACK_CODES)
    pack5 = next(item for item in payload["addons"] if item["code"] == "credits_5")
    assert pack5["kind"] == "credit_pack"
    assert pack5["credits_granted"] == 5
    assert pack5["unit_amount_cents"] == 500


@pytest.mark.asyncio
async def test_checkout_session_uses_payment_mode_for_credit_pack() -> None:
    user = User(
        id=uuid.uuid4(),
        email="pack-buyer@example.com",
        display_name="Buyer",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        credit_balance=0,
    )
    captured: dict[str, Any] = {}

    def _fake_create(**kwargs: Any) -> dict[str, str]:
        captured.update(kwargs)
        return {"id": "cs_pack", "url": "https://checkout.stripe.test/pack"}

    mock_session = AsyncMock()
    with (
        patch(
            "app.services.billing.subscription.resolve_price_id",
            new=AsyncMock(return_value="price_credits_5_test"),
        ),
        patch(
            "app.services.billing.subscription.stripe.checkout.Session.create",
            side_effect=_fake_create,
        ),
    ):
        result = await create_checkout_session(
            mock_session,
            user=user,
            code="credits_5",
            success_url="http://localhost:3100/billing?checkout=success",
            cancel_url="http://localhost:3100/billing?checkout=cancel",
        )

    assert captured["mode"] == "payment"
    assert result.session["url"].endswith("/pack")
