"""Apply admin-issued user grants."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.billing import CreditKind
from app.models.user import CreditTransaction
from app.services.admin.feature_unlocks import is_supported_feature_unlock, normalize_feature_name
from app.services.billing.credits import grant_credit


class InvalidGrantPayloadError(ValueError):
    """Raised when a grant payload fails validation."""


def validate_grant_payload(
    grant_type: AdminGrantType,
    payload: dict[str, Any],
) -> None:
    if grant_type == AdminGrantType.extra_credits:
        amount = payload.get("amount")
        if not isinstance(amount, int) or amount <= 0:
            raise InvalidGrantPayloadError(
                "extra_credits payload requires positive integer amount"
            )
        credit_kind = payload.get("credit_kind", "free")
        if credit_kind != CreditKind.free.value:
            raise InvalidGrantPayloadError(
                "extra_credits grants only support credit_kind='free'"
            )
        return

    if grant_type == AdminGrantType.tier_override:
        plan_code = payload.get("plan_code")
        if not isinstance(plan_code, str) or not plan_code.strip():
            raise InvalidGrantPayloadError(
                "tier_override payload requires non-empty plan_code"
            )
        return

    if grant_type == AdminGrantType.feature_unlock:
        feature = payload.get("feature")
        if not isinstance(feature, str) or not feature.strip():
            raise InvalidGrantPayloadError(
                "feature_unlock payload requires non-empty feature"
            )
        if not is_supported_feature_unlock(feature):
            raise InvalidGrantPayloadError(
                f"unsupported feature_unlock feature: {normalize_feature_name(feature)}"
            )
        return

    if grant_type == AdminGrantType.price_discount:
        promo_id = payload.get("stripe_promotion_code_id")
        if not isinstance(promo_id, str) or not promo_id.strip():
            raise InvalidGrantPayloadError(
                "price_discount payload requires stripe_promotion_code_id"
            )
        applicable = payload.get("applicable_plan_codes", [])
        if applicable is not None and not isinstance(applicable, list):
            raise InvalidGrantPayloadError(
                "applicable_plan_codes must be a list when provided"
            )
        if isinstance(applicable, list):
            for code in applicable:
                if not isinstance(code, str) or not code.strip():
                    raise InvalidGrantPayloadError(
                        "applicable_plan_codes entries must be non-empty strings"
                    )
        for optional_key in ("display_name", "headline"):
            value = payload.get(optional_key)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise InvalidGrantPayloadError(
                    f"{optional_key} must be a non-empty string when provided"
                )
        popup_enabled = payload.get("popup_enabled", False)
        if popup_enabled is not None and not isinstance(popup_enabled, bool):
            raise InvalidGrantPayloadError("popup_enabled must be a boolean when provided")
        popup_triggers = payload.get("popup_triggers")
        if popup_triggers is not None:
            if not isinstance(popup_triggers, list):
                raise InvalidGrantPayloadError("popup_triggers must be a list when provided")
            for trigger in popup_triggers:
                if trigger not in {"exit_intent", "post_exhaustion"}:
                    raise InvalidGrantPayloadError(
                        "popup_triggers entries must be exit_intent or post_exhaustion"
                    )
        return

    raise InvalidGrantPayloadError(f"unsupported grant_type: {grant_type.value}")


async def apply_extra_credits_grant(
    session: AsyncSession,
    *,
    grant: AdminUserGrant,
    admin_id: uuid.UUID,
) -> CreditTransaction:
    """Credit the user ledger for an ``extra_credits`` grant."""
    validate_grant_payload(AdminGrantType.extra_credits, grant.payload)
    amount = int(grant.payload["amount"])
    credit_kind = CreditKind(grant.payload.get("credit_kind", "free"))
    note = grant.payload.get("note")
    if note is not None and not isinstance(note, str):
        raise InvalidGrantPayloadError("note must be a string when provided")
    return await grant_credit(
        session,
        user_id=grant.user_id,
        credit_kind=credit_kind,
        delta=amount,
        reason="admin_user_grant",
        admin_id=admin_id,
        note=note or f"admin_user_grant:{grant.id}",
    )


async def apply_grant_side_effects(
    session: AsyncSession,
    *,
    grant: AdminUserGrant,
    admin_id: uuid.UUID,
) -> CreditTransaction | None:
    """Run immediate side effects for a newly created grant."""
    if grant.grant_type == AdminGrantType.extra_credits:
        return await apply_extra_credits_grant(session, grant=grant, admin_id=admin_id)
    return None


__all__ = [
    "InvalidGrantPayloadError",
    "apply_extra_credits_grant",
    "apply_grant_side_effects",
    "validate_grant_payload",
]
