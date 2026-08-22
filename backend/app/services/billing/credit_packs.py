"""One-time free-credit pack registry (M21 slice 5).

Replaces legacy ``better_pack`` / ``best_per_resume`` LLM add-on packs with
``CreditKind.free`` purchases exposed via ``/api/billing/prices`` addons.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.models.billing import CreditKind
from app.services.billing.exceptions import WebhookPayloadError

CREDIT_PACK_CODES: tuple[str, ...] = (
    "credits_5",
    "credits_15",
)


class CreditPackSpec(TypedDict):
    display_name: str
    credits_granted: int
    kind: str


CREDIT_PACK_SPECS: dict[str, CreditPackSpec] = {
    "credits_5": {
        "display_name": "5 credits",
        "credits_granted": 5,
        "kind": "credit_pack",
    },
    "credits_15": {
        "display_name": "15 credits",
        "credits_granted": 15,
        "kind": "credit_pack",
    },
}

# Retired from public checkout; webhook still fulfils in-flight purchases.
LEGACY_ONE_TIME_CODES: frozenset[str] = frozenset(
    {
        "better_pack",
        "better_5pack",
        "best_per_resume",
    }
)


def is_credit_pack_code(code: str) -> bool:
    return code in CREDIT_PACK_SPECS


def is_one_time_purchase_code(code: str | None) -> bool:
    if not code:
        return False
    return is_credit_pack_code(code) or code in LEGACY_ONE_TIME_CODES


def display_name_for_credit_pack(code: str) -> str:
    spec = CREDIT_PACK_SPECS.get(code)
    if spec is None:
        return code.replace("_", " ").title()
    return spec["display_name"]


def grant_for_one_time_code(code: str) -> tuple[CreditKind, int]:
    spec = CREDIT_PACK_SPECS.get(code)
    if spec is not None:
        return CreditKind.free, spec["credits_granted"]
    if code in {"better_pack", "better_5pack"}:
        return CreditKind.better, 5
    if code == "best_per_resume":
        return CreditKind.best, 1
    raise WebhookPayloadError(f"unknown one-time purchase code: {code!r}")


def credit_pack_addon_payload(
    *,
    code: str,
    amount_cents: int,
    stripe_price_id: str,
) -> dict[str, Any]:
    spec = CREDIT_PACK_SPECS[code]
    return {
        "code": code,
        "display_name": spec["display_name"],
        "kind": spec["kind"],
        "unit_amount_cents": amount_cents,
        "credits_granted": spec["credits_granted"],
        "stripe_price_id": stripe_price_id,
        "billing_cycle_requirement": None,
        "is_active": True,
    }


__all__ = [
    "CREDIT_PACK_CODES",
    "CREDIT_PACK_SPECS",
    "LEGACY_ONE_TIME_CODES",
    "credit_pack_addon_payload",
    "display_name_for_credit_pack",
    "grant_for_one_time_code",
    "is_credit_pack_code",
    "is_one_time_purchase_code",
]
