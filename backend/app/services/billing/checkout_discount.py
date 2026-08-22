"""Resolve checkout promo codes to Stripe promotion IDs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType
from app.services.billing.promo import _lookup_promo_for_compare, normalize_promo_code


@dataclass(frozen=True, slots=True)
class CheckoutDiscountResolution:
    stripe_promotion_code_id: str | None
    applied: bool
    message: str | None = None


async def resolve_checkout_discount(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    promo_code: str | None,
    plan_code: str,
) -> CheckoutDiscountResolution:
    """Validate a promo code for checkout and return a Stripe promotion id."""
    if promo_code is None or not promo_code.strip():
        return CheckoutDiscountResolution(None, False, None)

    normalized = normalize_promo_code(promo_code)
    if not normalized:
        return CheckoutDiscountResolution(
            None,
            False,
            "This promo code isn't valid.",
        )

    promo = await _lookup_promo_for_compare(session, normalized)
    if promo is None or promo.grant_type != AdminGrantType.price_discount:
        return CheckoutDiscountResolution(
            None,
            False,
            "This promo code isn't valid.",
        )

    if (
        promo.restricted_user_id is not None
        and promo.restricted_user_id != user_id
    ):
        return CheckoutDiscountResolution(
            None,
            False,
            "This promo code isn't valid.",
        )

    now = datetime.now(timezone.utc)
    if not promo.is_active:
        return CheckoutDiscountResolution(
            None,
            False,
            "This offer is no longer available.",
        )
    if promo.expires_at is not None and promo.expires_at <= now:
        return CheckoutDiscountResolution(
            None,
            False,
            "This offer has expired.",
        )
    if (
        promo.max_redemptions is not None
        and promo.redemption_count >= promo.max_redemptions
    ):
        return CheckoutDiscountResolution(
            None,
            False,
            "This offer has reached its redemption limit.",
        )

    payload = promo.payload or {}
    stripe_id = payload.get("stripe_promotion_code_id")
    if not isinstance(stripe_id, str) or not stripe_id.strip():
        return CheckoutDiscountResolution(
            None,
            False,
            "This promo code isn't valid.",
        )

    applicable = payload.get("applicable_plan_codes") or []
    if isinstance(applicable, list) and applicable and plan_code not in applicable:
        return CheckoutDiscountResolution(
            None,
            False,
            "This code doesn't apply to the selected plan.",
        )

    return CheckoutDiscountResolution(stripe_id.strip(), True, None)


__all__ = ["CheckoutDiscountResolution", "resolve_checkout_discount"]
