"""Unit tests for popup offer listing (M21 slice 4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.admin_grant import AdminGrantType
from app.models.promo_code import PromoCode
from app.services.billing.promo_offers import list_popup_offers, public_offer_view

pytestmark = pytest.mark.unit


def _popup_promo(*, code: str, popup_enabled: bool, redeemable: bool = True) -> PromoCode:
    expires = datetime.now(timezone.utc) + timedelta(days=3)
    return PromoCode(
        id=uuid.uuid4(),
        code=code,
        grant_type=AdminGrantType.price_discount,
        payload={
            "stripe_promotion_code_id": f"promo_{code.lower()}",
            "popup_enabled": popup_enabled,
            "popup_triggers": ["exit_intent", "post_exhaustion"],
        },
        expires_at=expires if redeemable else datetime.now(timezone.utc) - timedelta(hours=1),
        is_active=True,
    )


@pytest.mark.asyncio
async def test_list_popup_offers_filters_non_popup_and_expired() -> None:
    active_popup = _popup_promo(code="ACTIVE", popup_enabled=True)
    hidden = _popup_promo(code="HIDDEN", popup_enabled=False)
    expired = _popup_promo(code="EXPIRED", popup_enabled=True, redeemable=False)

    class FakeScalars:
        def all(self) -> list[PromoCode]:
            return [active_popup, hidden, expired]

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=FakeResult())

    offers = await list_popup_offers(mock_session)

    assert len(offers) == 1
    assert offers[0].code == "ACTIVE"
    assert offers[0].popup_triggers == ["exit_intent", "post_exhaustion"]


@pytest.mark.asyncio
async def test_list_popup_offers_excludes_user_redemptions() -> None:
    user_id = uuid.uuid4()
    redeemed = _popup_promo(code="USED", popup_enabled=True)
    available = _popup_promo(code="FRESH", popup_enabled=True)

    class FakeScalars:
        def __init__(self, rows: list) -> None:
            self._rows = rows

        def all(self) -> list:
            return self._rows

    class FakeResult:
        def __init__(self, rows: list) -> None:
            self._rows = rows

        def scalars(self) -> FakeScalars:
            return FakeScalars(self._rows)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            FakeResult([redeemed, available]),
            FakeResult([redeemed.id]),
        ]
    )

    offers = await list_popup_offers(mock_session, user_id=user_id)

    assert len(offers) == 1
    assert offers[0].code == "FRESH"


def test_public_offer_view_defaults_popup_disabled() -> None:
    promo = PromoCode(
        id=uuid.uuid4(),
        code="PLAIN",
        grant_type=AdminGrantType.price_discount,
        payload={"stripe_promotion_code_id": "promo_plain"},
    )
    view = public_offer_view(promo)
    assert view.popup_enabled is False
    assert view.popup_triggers == []
