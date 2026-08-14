"""Promo code redemption — timing-safe lookup and grant application."""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.promo_code import PromoCode, PromoRedemption
from app.models.billing import CreditKind
from app.models.user import CreditTransaction
from app.services.admin.grants import InvalidGrantPayloadError, validate_grant_payload
from app.services.billing.credits import grant_credit


class PromoRedeemError(Exception):
    """Base error for promo redemption failures."""

    code: str

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


class PromoCodeInvalidError(PromoRedeemError):
    def __init__(self) -> None:
        super().__init__("promo_code_invalid")


class PromoCodeExpiredError(PromoRedeemError):
    def __init__(self) -> None:
        super().__init__("promo_code_expired")


class PromoCodeExhaustedError(PromoRedeemError):
    def __init__(self) -> None:
        super().__init__("promo_code_exhausted")


class PromoCodeInactiveError(PromoRedeemError):
    def __init__(self) -> None:
        super().__init__("promo_code_inactive")


@dataclass(frozen=True, slots=True)
class PromoRedeemResult:
    promo_code_id: uuid.UUID
    grant_type: AdminGrantType
    payload: dict
    redemption_id: uuid.UUID
    idempotent: bool
    credit_transaction_id: uuid.UUID | None = None
    admin_user_grant_id: uuid.UUID | None = None


def normalize_promo_code(code: str) -> str:
    return code.strip().upper()


def codes_match(stored: str, provided: str) -> bool:
    if len(stored) != len(provided):
        return False
    return hmac.compare_digest(stored, provided)


async def _lookup_promo_for_compare(
    session: AsyncSession,
    normalized_code: str,
) -> PromoCode | None:
    """Resolve a promo row using a constant-time code comparison."""
    row = (
        await session.execute(
            select(PromoCode).where(PromoCode.code == normalized_code)
        )
    ).scalar_one_or_none()
    if row is None:
        hmac.compare_digest(normalized_code, normalized_code)
        return None
    if not codes_match(row.code, normalized_code):
        return None
    return row


async def redeem_promo_code(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    code: str,
) -> PromoRedeemResult:
    normalized = normalize_promo_code(code)
    if not normalized:
        raise PromoCodeInvalidError()

    promo = await _lookup_promo_for_compare(session, normalized)
    if promo is None:
        raise PromoCodeInvalidError()

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
        return PromoRedeemResult(
            promo_code_id=promo.id,
            grant_type=promo.grant_type,
            payload=dict(promo.payload or {}),
            redemption_id=existing.id,
            idempotent=True,
        )

    now = datetime.now(timezone.utc)
    if not promo.is_active:
        raise PromoCodeInactiveError()
    if promo.expires_at is not None and promo.expires_at <= now:
        raise PromoCodeExpiredError()
    if (
        promo.max_redemptions is not None
        and promo.redemption_count >= promo.max_redemptions
    ):
        raise PromoCodeExhaustedError()

    validate_grant_payload(promo.grant_type, promo.payload)

    redemption = PromoRedemption(
        id=uuid.uuid4(),
        promo_code_id=promo.id,
        user_id=user_id,
        redeemed_at=now,
    )
    session.add(redemption)
    promo.redemption_count += 1

    grant = AdminUserGrant(
        id=uuid.uuid4(),
        user_id=user_id,
        grant_type=promo.grant_type,
        payload=dict(promo.payload or {}),
        expires_at=promo.expires_at,
        created_by_admin_id=promo.created_by_admin_id,
        created_at=now,
    )
    session.add(grant)
    await session.flush()

    credit_tx: CreditTransaction | None = None
    if promo.grant_type == AdminGrantType.extra_credits:
        amount = int(promo.payload["amount"])
        credit_kind = CreditKind(promo.payload.get("credit_kind", "free"))
        credit_tx = await grant_credit(
            session,
            user_id=user_id,
            credit_kind=credit_kind,
            delta=amount,
            reason="promo_redeem",
            admin_id=promo.created_by_admin_id,
            note=f"promo_redeem:{promo.id}",
        )

    await session.flush()
    return PromoRedeemResult(
        promo_code_id=promo.id,
        grant_type=promo.grant_type,
        payload=dict(promo.payload or {}),
        redemption_id=redemption.id,
        idempotent=False,
        credit_transaction_id=credit_tx.id if credit_tx is not None else None,
        admin_user_grant_id=grant.id,
    )


__all__ = [
    "InvalidGrantPayloadError",
    "PromoCodeExhaustedError",
    "PromoCodeExpiredError",
    "PromoCodeInactiveError",
    "PromoCodeInvalidError",
    "PromoRedeemError",
    "PromoRedeemResult",
    "codes_match",
    "normalize_promo_code",
    "redeem_promo_code",
]
