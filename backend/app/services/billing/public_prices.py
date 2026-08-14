"""Public billing price list from active ``PlanConfig`` rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import PlanConfig, PlanConfigInterval

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
    plans: list[dict[str, Any]] = []
    latest = datetime(1970, 1, 1, tzinfo=timezone.utc)
    currency = settings.BILLING_CURRENCY or "USD"

    for row in rows:
        if row.code not in PUBLIC_PLAN_CODES or row.code in seen:
            continue
        seen.add(row.code)
        if row.created_at > latest:
            latest = row.created_at
        plans.append(
            {
                "code": row.code,
                "display_name": _DISPLAY_NAMES.get(
                    row.code, row.code.replace("_", " ").title()
                ),
                "cycle": _cycle_for_row(row.code, row.interval),
                "amount_cents": row.amount_cents,
                "trial_days": 7 if row.code.startswith("monthly_") else None,
                "stripe_price_id": row.stripe_price_id,
                "is_active": True,
                "features": _FEATURES_BY_CODE.get(row.code, ["resume_tailor"]),
            }
        )

    return {
        "version": f"plans-{latest.isoformat()}",
        "currency": currency,
        "plans": plans,
        "addons": [],
    }


__all__ = ["PUBLIC_PLAN_CODES", "build_public_billing_prices"]
