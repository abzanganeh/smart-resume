"""Stripe Checkout wallet payment options (Apple Pay, Google Pay)."""

from __future__ import annotations

from typing import Any

from app.config import settings


def checkout_wallet_kwargs() -> dict[str, Any]:
    """Kwargs for ``stripe.checkout.Session.create`` to surface wallet buttons.

    Uses Stripe automatic payment methods so Apple Pay and Google Pay appear on
    supported devices without enabling PayPal or other redirect-heavy methods
    we have not validated for subscriptions in every market.
    """
    if not settings.STRIPE_CHECKOUT_WALLETS_ENABLED:
        return {}
    return {
        "automatic_payment_methods": {
            "enabled": True,
            "allow_redirects": "never",
        },
    }


__all__ = ["checkout_wallet_kwargs"]
