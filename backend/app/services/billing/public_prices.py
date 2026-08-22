"""Public billing price list from active ``PlanConfig`` rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import PlanConfig, PlanConfigInterval
from app.services.billing.credit_packs import (
    CREDIT_PACK_CODES,
    credit_pack_addon_payload,
)
from app.services.billing.tier_limits import seed_row_for_plan

# Base subscription codes exposed on /billing (legacy LLM add-ons excluded).
PUBLIC_PLAN_CODES: frozenset[str] = frozenset(
    {
        "weekly",
        "monthly_pro",
        "yearly_pro",
        "monthly_plus",
        "yearly_plus",
        "monthly_premium",
        "yearly_premium",
    }
)

_DISPLAY_NAMES: dict[str, str] = {
    "weekly": "Weekly",
    "monthly_pro": "Pro",
    "yearly_pro": "Pro",
    "monthly_plus": "Pro+",
    "yearly_plus": "Pro+",
    "monthly_premium": "Premium",
    "yearly_premium": "Premium",
}

_CYCLE_BY_CODE: dict[str, str] = {
    "weekly": "weekly",
    "monthly_pro": "monthly",
    "yearly_pro": "yearly",
    "monthly_plus": "monthly",
    "yearly_plus": "yearly",
    "monthly_premium": "monthly",
    "yearly_premium": "yearly",
}

_FEATURES_BY_CODE: dict[str, list[str]] = {
    "weekly": ["resume_tailor", "cover_letter", "fit_analysis", "job_search"],
    "monthly_pro": [
        "resume_tailor",
        "cover_letter",
        "fit_analysis",
        "job_search",
        "master_resume",
        "ats_guidance",
    ],
    "monthly_plus": [
        "resume_tailor",
        "cover_letter",
        "fit_analysis",
        "job_search",
        "master_resume",
        "ats_guidance",
    ],
    "monthly_premium": [
        "resume_tailor",
        "cover_letter",
        "fit_analysis",
        "job_search",
        "master_resume",
        "ats_guidance",
    ],
    "yearly_pro": [
        "resume_tailor",
        "cover_letter",
        "fit_analysis",
        "job_search",
        "master_resume",
        "ats_guidance",
    ],
    "yearly_plus": [
        "resume_tailor",
        "cover_letter",
        "fit_analysis",
        "job_search",
        "master_resume",
        "ats_guidance",
    ],
    "yearly_premium": [
        "resume_tailor",
        "cover_letter",
        "fit_analysis",
        "job_search",
        "master_resume",
        "ats_guidance",
    ],
}


def _cycle_for_row(code: str, interval: PlanConfigInterval) -> str:
    if interval == PlanConfigInterval.week:
        return "weekly"
    if interval == PlanConfigInterval.year:
        return "yearly"
    if interval == PlanConfigInterval.day:
        return "daily"
    return _CYCLE_BY_CODE.get(code, "monthly")


async def build_public_billing_prices(session: AsyncSession) -> dict[str, Any]:
    """Return IMPLEMENTATION_PLAN §6 ``GET /api/billing/prices`` payload."""
    now = datetime.now(timezone.utc)
    rows = list(
        (
            await session.execute(
                select(PlanConfig)
                .where(PlanConfig.is_active.is_(True))
                .where(PlanConfig.effective_from <= now)
                .where(
                    (PlanConfig.effective_to.is_(None))
                    | (PlanConfig.effective_to > now)
                )
                .order_by(PlanConfig.code, PlanConfig.effective_from.desc())
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    pack_rows: dict[str, PlanConfig] = {}
    plans: list[dict[str, Any]] = []
    latest = datetime(1970, 1, 1, tzinfo=timezone.utc)
    currency = settings.BILLING_CURRENCY or "USD"

    for row in rows:
        if row.code in CREDIT_PACK_CODES and row.code not in pack_rows:
            pack_rows[row.code] = row
            if row.created_at > latest:
                latest = row.created_at
        if row.code not in PUBLIC_PLAN_CODES or row.code in seen:
            continue
        seen.add(row.code)
        if row.created_at > latest:
            latest = row.created_at
        plans.append(
            {
                "code": row.code,
                "display_name": display_name_for_plan_code(row.code),
                "cycle": _cycle_for_row(row.code, row.interval),
                "amount_cents": row.amount_cents,
                # No trial is configured in Stripe checkout — do not advertise one.
                "trial_days": None,
                "stripe_price_id": row.stripe_price_id,
                "is_active": True,
                "features": _FEATURES_BY_CODE.get(row.code, ["resume_tailor"]),
                "limits": _public_limits_for_plan(row.code),
            }
        )

    addons = [
        credit_pack_addon_payload(
            code=code,
            amount_cents=pack_rows[code].amount_cents,
            stripe_price_id=pack_rows[code].stripe_price_id,
        )
        for code in CREDIT_PACK_CODES
        if code in pack_rows
    ]

    return {
        "version": f"plans-{latest.isoformat()}",
        "currency": currency,
        "plans": plans,
        "addons": addons,
    }


def _public_limits_for_plan(plan_code: str) -> dict[str, int | None] | None:
    """Per-period allowances advertised on a plan card.

    Sourced from the tier-limits seed so marketing copy cannot drift from the
    numbers the quota layer actually enforces. ``None`` for a field means the
    plan has no cap on that action.
    """
    row = seed_row_for_plan(plan_code)
    if row is None:
        return None
    return {
        "resumes_per_period": row["resumes_per_period"],
        "searches_per_period": row["searches_per_period"],
        "fit_analyses_per_period": row["fit_analyses_per_period"],
        "whisper_uses_per_period": row["whisper_uses_per_period"],
        "career_watch_companies": row["career_watch_companies"],
    }


def display_name_for_plan_code(plan_code: str) -> str:
    """Marketing label for a canonical plan code (``monthly_pro`` -> ``Pro``)."""
    return _DISPLAY_NAMES.get(plan_code, plan_code.replace("_", " ").title())


__all__ = [
    "PUBLIC_PLAN_CODES",
    "build_public_billing_prices",
    "display_name_for_plan_code",
]
