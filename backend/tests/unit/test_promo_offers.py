"""Unit tests for price-discount offer helpers (M21 slice 2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.admin_grant import AdminGrantType
from app.models.promo_code import PromoCode
from app.services.admin.grants import InvalidGrantPayloadError, validate_grant_payload
from app.services.billing.promo_offers import (
    build_price_discount_payload,
    offer_summary_for_promo,
    public_offer_view,
    remaining_redemptions,
)

pytestmark = pytest.mark.unit


def test_build_price_discount_payload() -> None:
    payload = build_price_discount_payload(
        stripe_promotion_code_id="promo_abc",
        applicable_plan_codes=["monthly_pro"],
        display_name="Launch 40% off",
        headline="Limited-time upgrade",
    )
    assert payload["stripe_promotion_code_id"] == "promo_abc"
    assert payload["applicable_plan_codes"] == ["monthly_pro"]
    assert payload["display_name"] == "Launch 40% off"


def test_validate_price_discount_payload() -> None:
    validate_grant_payload(
        AdminGrantType.price_discount,
        build_price_discount_payload(stripe_promotion_code_id="promo_abc"),
    )


def test_validate_price_discount_rejects_empty_stripe_id() -> None:
    with pytest.raises(InvalidGrantPayloadError):
        validate_grant_payload(
            AdminGrantType.price_discount,
            {"stripe_promotion_code_id": "  "},
        )


def test_offer_summary_for_price_discount_uses_display_name() -> None:
    promo = PromoCode(
        id=uuid.uuid4(),
        code="SAVE40",
        grant_type=AdminGrantType.price_discount,
        payload={
            "stripe_promotion_code_id": "promo_abc",
            "display_name": "Summer sale",
        },
    )
    assert offer_summary_for_promo(promo) == "Summer sale"


def test_public_offer_view_omits_stripe_secret() -> None:
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    promo = PromoCode(
        id=uuid.uuid4(),
        code="SAVE40",
        grant_type=AdminGrantType.price_discount,
        payload={
            "stripe_promotion_code_id": "promo_secret",
            "display_name": "Summer sale",
            "headline": "40% off Pro",
            "applicable_plan_codes": ["monthly_pro"],
        },
        expires_at=expires,
        max_redemptions=100,
        redemption_count=3,
        is_active=True,
    )
    view = public_offer_view(promo).to_dict()
    assert "stripe_promotion_code_id" not in view
    assert view["display_name"] == "Summer sale"
    assert view["applicable_plan_codes"] == ["monthly_pro"]
    assert view["is_redeemable"] is True


def test_remaining_redemptions() -> None:
    promo = PromoCode(
        id=uuid.uuid4(),
        code="X",
        grant_type=AdminGrantType.price_discount,
        payload={"stripe_promotion_code_id": "promo_x"},
        max_redemptions=10,
        redemption_count=4,
    )
    assert remaining_redemptions(promo) == 6
