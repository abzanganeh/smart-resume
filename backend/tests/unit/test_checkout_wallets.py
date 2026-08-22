"""Unit tests for Stripe Checkout wallet payment options (M21 slice 6)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.checkout_wallets import checkout_wallet_kwargs
from app.services.billing.subscription import create_checkout_session

pytestmark = pytest.mark.unit


def test_checkout_wallet_kwargs_enabled_by_default() -> None:
    with patch.object(settings, "STRIPE_CHECKOUT_WALLETS_ENABLED", True):
        kwargs = checkout_wallet_kwargs()
    assert kwargs["automatic_payment_methods"]["enabled"] is True
    assert kwargs["automatic_payment_methods"]["allow_redirects"] == "never"


def test_checkout_wallet_kwargs_disabled_returns_empty() -> None:
    with patch.object(settings, "STRIPE_CHECKOUT_WALLETS_ENABLED", False):
        assert checkout_wallet_kwargs() == {}


@pytest.mark.asyncio
async def test_create_checkout_session_enables_wallet_payment_methods() -> None:
    user = User(
        id=uuid.uuid4(),
        email="wallet@example.com",
        display_name="Wallet",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        credit_balance=0,
    )
    captured: dict[str, Any] = {}

    def _fake_create(**kwargs: Any) -> dict[str, str]:
        captured.update(kwargs)
        return {"id": "cs_wallet", "url": "https://checkout.stripe.test/wallet"}

    mock_session = AsyncMock()
    with (
        patch.object(settings, "STRIPE_CHECKOUT_WALLETS_ENABLED", True),
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
            success_url="http://localhost:3100/billing?checkout=success",
            cancel_url="http://localhost:3100/billing?checkout=cancel",
        )

    assert captured["automatic_payment_methods"] == {
        "enabled": True,
        "allow_redirects": "never",
    }
