"""Unit tests for checkout discount plumbing (M21 slice 1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType
from app.models.promo_code import PromoCode, PromoRedemption
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.checkout_discount import resolve_checkout_discount
from app.services.billing.promo import PromoCodeInvalidError, redeem_promo_code
from app.services.billing.subscription import CheckoutSessionResult, create_checkout_session

pytestmark = pytest.mark.unit


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        email="buyer@example.com",
        display_name="Buyer",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        credit_balance=0,
    )


async def _seed_discount_promo(
    db_session: AsyncSession,
    *,
    code: str = "SAVE40",
    stripe_promotion_code_id: str = "promo_test_40",
    applicable_plan_codes: list[str] | None = None,
    expires_at: datetime | None = None,
    max_redemptions: int | None = None,
    redemption_count: int = 0,
    is_active: bool = True,
) -> PromoCode:
    promo = PromoCode(
        id=uuid.uuid4(),
        code=code,
        grant_type=AdminGrantType.price_discount,
        payload={
            "stripe_promotion_code_id": stripe_promotion_code_id,
            "applicable_plan_codes": applicable_plan_codes or [],
        },
        max_redemptions=max_redemptions,
        redemption_count=redemption_count,
        expires_at=expires_at,
        is_active=is_active,
    )
    db_session.add(promo)
    await db_session.flush()
    return promo


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_checkout_discount_applies_valid_code(
    db_session: AsyncSession,
) -> None:
    user = _user()
    await _seed_discount_promo(
        db_session,
        applicable_plan_codes=["monthly_pro"],
    )
    result = await resolve_checkout_discount(
        db_session,
        user_id=user.id,
        promo_code="save40",
        plan_code="monthly_pro",
    )
    assert result.applied is True
    assert result.stripe_promotion_code_id == "promo_test_40"
    assert result.message is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_checkout_discount_rejects_forged_code(
    db_session: AsyncSession,
) -> None:
    user = _user()
    await _seed_discount_promo(db_session, code="REALCODE")
    result = await resolve_checkout_discount(
        db_session,
        user_id=user.id,
        promo_code="FAKECODE",
        plan_code="monthly_pro",
    )
    assert result.applied is False
    assert result.stripe_promotion_code_id is None
    assert result.message is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_checkout_discount_expired_falls_back(
    db_session: AsyncSession,
) -> None:
    user = _user()
    await _seed_discount_promo(
        db_session,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    result = await resolve_checkout_discount(
        db_session,
        user_id=user.id,
        promo_code="SAVE40",
        plan_code="monthly_pro",
    )
    assert result.applied is False
    assert "expired" in (result.message or "").lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_checkout_discount_exhausted_falls_back(
    db_session: AsyncSession,
) -> None:
    user = _user()
    await _seed_discount_promo(
        db_session,
        max_redemptions=1,
        redemption_count=1,
    )
    result = await resolve_checkout_discount(
        db_session,
        user_id=user.id,
        promo_code="SAVE40",
        plan_code="monthly_pro",
    )
    assert result.applied is False
    assert "limit" in (result.message or "").lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_checkout_discount_wrong_plan_falls_back(
    db_session: AsyncSession,
) -> None:
    user = _user()
    await _seed_discount_promo(
        db_session,
        applicable_plan_codes=["yearly_pro"],
    )
    result = await resolve_checkout_discount(
        db_session,
        user_id=user.id,
        promo_code="SAVE40",
        plan_code="monthly_pro",
    )
    assert result.applied is False
    assert "doesn't apply" in (result.message or "").lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_checkout_discount_rejects_prior_user_redemption(
    db_session: AsyncSession,
) -> None:
    user = _user()
    db_session.add(user)
    promo = await _seed_discount_promo(db_session)
    db_session.add(
        PromoRedemption(
            id=uuid.uuid4(),
            promo_code_id=promo.id,
            user_id=user.id,
            redeemed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()
    result = await resolve_checkout_discount(
        db_session,
        user_id=user.id,
        promo_code="SAVE40",
        plan_code="monthly_pro",
    )
    assert result.applied is False
    assert "already" in (result.message or "").lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redeem_price_discount_is_checkout_only(
    db_session: AsyncSession,
) -> None:
    user = _user()
    db_session.add(user)
    await _seed_discount_promo(db_session)
    await db_session.flush()
    with pytest.raises(PromoCodeInvalidError):
        await redeem_promo_code(
            db_session,
            user_id=user.id,
            code="SAVE40",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_pre_applies_stripe_discount() -> None:
    user = _user()
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
            "app.services.billing.subscription.resolve_checkout_discount",
            new=AsyncMock(
                return_value=type(
                    "R",
                    (),
                    {
                        "stripe_promotion_code_id": "promo_test_40",
                        "applied": True,
                        "message": None,
                    },
                )()
            ),
        ),
        patch(
            "app.services.billing.subscription.stripe.checkout.Session.create",
            side_effect=_fake_create,
        ),
    ):
        result = await create_checkout_session(
            mock_session,
            user=user,
            code="monthly_pro",
            success_url="http://localhost:3100/success",
            cancel_url="http://localhost:3100/cancel",
            promo_code="SAVE40",
        )

    assert isinstance(result, CheckoutSessionResult)
    assert result.discount_applied is True
    assert captured["discounts"] == [{"promotion_code": "promo_test_40"}]
    assert "allow_promotion_codes" not in captured


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_promo_still_checkouts() -> None:
    user = _user()
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
            "app.services.billing.subscription.resolve_checkout_discount",
            new=AsyncMock(
                return_value=type(
                    "R",
                    (),
                    {
                        "stripe_promotion_code_id": None,
                        "applied": False,
                        "message": "This offer has expired.",
                    },
                )()
            ),
        ),
        patch(
            "app.services.billing.subscription.stripe.checkout.Session.create",
            side_effect=_fake_create,
        ),
    ):
        result = await create_checkout_session(
            mock_session,
            user=user,
            code="monthly_pro",
            success_url="http://localhost:3100/success",
            cancel_url="http://localhost:3100/cancel",
            promo_code="EXPIRED",
        )

    assert result.discount_applied is False
    assert result.discount_message == "This offer has expired."
    assert "discounts" not in captured
