"""Contextual upgrade payload when free credits are exhausted."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import CreditKind
from app.models.user import User
from app.services.billing.credit_spend import (
    credits_locked_until_verification,
    spendable_free_credits,
)
from app.services.billing.credits import get_balance
from app.services.billing.exceptions import InsufficientCreditsError
from app.services.billing.exhaustion_top_up import get_exhaustion_top_up_eligibility
from app.services.billing.public_prices import build_public_billing_prices

# Canonical entry plans shown at credit exhaustion (cheap door → annual).
EXHAUSTION_PAYWALL_PLAN_CODES: tuple[str, ...] = (
    "weekly",
    "monthly_pro",
    "yearly_pro",
)

HIGHLIGHT_PLAN_CODE = "monthly_pro"

FREE_STILL_AVAILABLE: tuple[dict[str, str], ...] = (
    {
        "id": "job_search",
        "label": "Job search on the free corpus",
        "path": "/jobs",
    },
    {
        "id": "tracker",
        "label": "Application tracker",
        "path": "/tracker",
    },
    {
        "id": "master_resume",
        "label": "Master resume profile",
        "path": "/profile",
    },
)

_PAYWALL_HEADLINE = "You're out of credits for AI tailoring"
_PAYWALL_MESSAGE = (
    "Credits pay for resume tailoring, cover letters, section regeneration, and "
    "similar AI actions. Subscribe for a monthly allowance plus job search, fit "
    "analysis, and Whisper voice — or keep using the free tools below."
)


def _filter_upgrade_plans(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {code: idx for idx, code in enumerate(EXHAUSTION_PAYWALL_PLAN_CODES)}
    filtered = [plan for plan in plans if plan.get("code") in order]
    filtered.sort(key=lambda plan: order.get(str(plan.get("code")), 99))
    return filtered


def _yearly_savings_percent(plans: list[dict[str, Any]]) -> int | None:
    monthly = next((p for p in plans if p.get("code") == "monthly_pro"), None)
    yearly = next((p for p in plans if p.get("code") == "yearly_pro"), None)
    if not monthly or not yearly:
        return None
    monthly_cents = int(monthly.get("amount_cents") or 0)
    yearly_cents = int(yearly.get("amount_cents") or 0)
    if monthly_cents <= 0 or yearly_cents <= 0:
        return None
    pct = round((1 - yearly_cents / (monthly_cents * 12)) * 100)
    return pct if pct > 0 else None


async def build_exhaustion_paywall(
    session: AsyncSession,
    *,
    user: User,
) -> dict[str, Any]:
    """Return structured upgrade + free-tier context for credit exhaustion."""
    prices = await build_public_billing_prices(session)
    upgrade_plans = _filter_upgrade_plans(list(prices.get("plans") or []))

    free_credits = await get_balance(
        session,
        user_id=user.id,
        credit_kind=CreditKind.free,
    )
    top_up = await get_exhaustion_top_up_eligibility(session, user=user)

    return {
        "headline": _PAYWALL_HEADLINE,
        "message": _PAYWALL_MESSAGE,
        "credit_balance": free_credits,
        "spendable_credit_balance": spendable_free_credits(user, balance=free_credits),
        "credits_locked_until_verification": credits_locked_until_verification(
            user,
            balance=free_credits,
        ),
        "free_still_available": list(FREE_STILL_AVAILABLE),
        "upgrade_plans": upgrade_plans,
        "currency": prices.get("currency") or settings.BILLING_CURRENCY or "USD",
        "highlight_plan_code": HIGHLIGHT_PLAN_CODE,
        "yearly_savings_percent": _yearly_savings_percent(upgrade_plans),
        "exhaustion_top_up_eligible": top_up.eligible,
        "exhaustion_top_up_amount": top_up.amount,
    }


async def insufficient_credits_detail(
    session: AsyncSession,
    *,
    user: User,
    exc: InsufficientCreditsError | None = None,
    message: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    """HTTP 402 detail with embedded paywall payload for inline UI."""
    paywall = await build_exhaustion_paywall(session, user=user)
    detail: dict[str, Any] = {
        "code": "insufficient_credits",
        "message": message
        or "You're out of credits. Pick a plan below or use the free tools that still work.",
        "paywall": paywall,
    }
    if action:
        detail["action"] = action
    if exc is not None:
        detail["credit_kind"] = exc.credit_kind
        detail["balance"] = exc.balance
    return detail


__all__ = [
    "EXHAUSTION_PAYWALL_PLAN_CODES",
    "FREE_STILL_AVAILABLE",
    "build_exhaustion_paywall",
    "insufficient_credits_detail",
]
