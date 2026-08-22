"""Price-discount offer helpers for checkout promos (M21)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType
from app.models.promo_code import PromoCode, PromoRedemption
from app.services.billing.promo import _lookup_promo_for_compare, normalize_promo_code


@dataclass(frozen=True, slots=True)
class PublicOfferView:
    code: str
    grant_type: AdminGrantType
    expires_at: datetime | None
    is_active: bool
    applicable_plan_codes: list[str]
    display_name: str | None
    headline: str | None
    redemption_count: int
    max_redemptions: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "grant_type": self.grant_type.value,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "is_redeemable": self.is_active
            and (
                self.expires_at is None or self.expires_at > datetime.now(timezone.utc)
            )
            and (
                self.max_redemptions is None
                or self.redemption_count < self.max_redemptions
            ),
            "applicable_plan_codes": self.applicable_plan_codes,
            "display_name": self.display_name,
            "headline": self.headline,
            "redemption_count": self.redemption_count,
            "max_redemptions": self.max_redemptions,
        }


def build_price_discount_payload(
    *,
    stripe_promotion_code_id: str,
    applicable_plan_codes: list[str] | None = None,
    display_name: str | None = None,
    headline: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stripe_promotion_code_id": stripe_promotion_code_id.strip(),
        "applicable_plan_codes": applicable_plan_codes or [],
    }
    if display_name and display_name.strip():
        payload["display_name"] = display_name.strip()
    if headline and headline.strip():
        payload["headline"] = headline.strip()
    return payload


def offer_summary_for_promo(promo: PromoCode) -> str:
    payload = promo.payload or {}
    if promo.grant_type == AdminGrantType.price_discount:
        display = payload.get("display_name")
        if isinstance(display, str) and display.strip():
            return display.strip()
        plans = payload.get("applicable_plan_codes") or []
        if isinstance(plans, list) and plans:
            return f"Checkout discount ({', '.join(str(p) for p in plans)})"
        return "Checkout discount"
    if promo.grant_type == AdminGrantType.extra_credits:
        amount = payload.get("amount")
        return f"{amount} bonus credits" if amount is not None else "Bonus credits"
    if promo.grant_type == AdminGrantType.feature_unlock:
        feature = payload.get("feature")
        return f"Unlock {feature}" if feature else "Feature unlock"
    if promo.grant_type == AdminGrantType.tier_override:
        plan = payload.get("plan_code")
        return f"Tier override ({plan})" if plan else "Tier override"
    return promo.grant_type.value


def remaining_redemptions(promo: PromoCode) -> int | None:
    if promo.max_redemptions is None:
        return None
    return max(0, promo.max_redemptions - promo.redemption_count)


def public_offer_view(promo: PromoCode) -> PublicOfferView:
    payload = promo.payload or {}
    applicable = payload.get("applicable_plan_codes") or []
    if not isinstance(applicable, list):
        applicable = []
    display_name = payload.get("display_name")
    headline = payload.get("headline")
    return PublicOfferView(
        code=promo.code,
        grant_type=promo.grant_type,
        expires_at=promo.expires_at,
        is_active=promo.is_active,
        applicable_plan_codes=[str(code) for code in applicable],
        display_name=display_name if isinstance(display_name, str) else None,
        headline=headline if isinstance(headline, str) else None,
        redemption_count=promo.redemption_count,
        max_redemptions=promo.max_redemptions,
    )


async def lookup_public_offer(
    session: AsyncSession,
    *,
    code: str,
) -> PublicOfferView | None:
    normalized = normalize_promo_code(code)
    if not normalized:
        return None
    promo = await _lookup_promo_for_compare(session, normalized)
    if promo is None or promo.grant_type != AdminGrantType.price_discount:
        return None
    return public_offer_view(promo)


async def record_checkout_promo_redemption(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    promo_code: str,
) -> bool:
    """Persist a checkout discount redemption after successful payment."""
    normalized = normalize_promo_code(promo_code)
    if not normalized:
        return False

    promo = await _lookup_promo_for_compare(session, normalized)
    if promo is None or promo.grant_type != AdminGrantType.price_discount:
        return False

    promo = (
        await session.execute(
            select(PromoCode).where(PromoCode.id == promo.id).with_for_update()
        )
    ).scalar_one()

    existing = (
        await session.execute(
            select(PromoRedemption)
            .where(PromoRedemption.promo_code_id == promo.id)
            .where(PromoRedemption.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    now = datetime.now(timezone.utc)
    if not promo.is_redeemable:
        return False

    session.add(
        PromoRedemption(
            id=uuid.uuid4(),
            promo_code_id=promo.id,
            user_id=user_id,
            redeemed_at=now,
        )
    )
    promo.redemption_count += 1
    await session.flush()
    return True


__all__ = [
    "PublicOfferView",
    "build_price_discount_payload",
    "lookup_public_offer",
    "offer_summary_for_promo",
    "public_offer_view",
    "record_checkout_promo_redemption",
    "remaining_redemptions",
]
