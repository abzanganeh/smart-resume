"""Boot-time helpers for the billing surface.

- :func:`seed_plan_configs_if_empty` reads ``STRIPE_PRICE_*`` env vars
  and inserts one ``PlanConfig`` row per canonical code from
  IMPLEMENTATION_PLAN §7.1.  No-op if any rows already exist (admin is
  the source of truth once seeded).
- :func:`assert_canonical_codes_resolve` runs at startup and emits a
  ``startup_price_gap`` warning per missing code.  CI's staging gate
  may treat any gap as a failed deploy; production silently degrades
  to env fallback (still served by ``resolve_price_id``).
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import PlanConfig, PlanConfigInterval
from app.services.billing.price_resolver import (
    CANONICAL_CODES,
    ENV_VAR_BY_CODE,
    _env_price_for,
    assert_all_codes_resolve,
)

log = structlog.get_logger("billing.bootstrap")


_INTERVAL_BY_CODE: dict[str, PlanConfigInterval] = {
    "daily": PlanConfigInterval.day,
    "weekly": PlanConfigInterval.week,
    "monthly": PlanConfigInterval.month,
    "monthly_yearly": PlanConfigInterval.year,
    "better_pack": PlanConfigInterval.one_time,
    "better_monthly": PlanConfigInterval.month,
    "better_yearly": PlanConfigInterval.year,
    "best_per_resume": PlanConfigInterval.one_time,
    "best_monthly": PlanConfigInterval.month,
    "best_yearly": PlanConfigInterval.year,
}

_ELIGIBILITY_BY_CODE: dict[str, str] = {
    "daily": "base_plan",
    "weekly": "base_plan",
    "monthly": "base_plan",
    "monthly_yearly": "base_plan",
    "better_pack": "credit_pack",
    "better_monthly": "addon_subscription",
    "better_yearly": "addon_subscription",
    "best_per_resume": "per_resume",
    "best_monthly": "addon_subscription",
    "best_yearly": "addon_subscription",
}


async def seed_plan_configs_if_empty(session: AsyncSession) -> int:
    """Insert one row per canonical code; no-op if any rows already exist.

    Returns the number of rows inserted (0 means already seeded).
    """
    existing_count = (
        await session.execute(select(func.count()).select_from(PlanConfig))
    ).scalar() or 0
    if existing_count > 0:
        log.info("billing.bootstrap.plan_configs_already_seeded", count=existing_count)
        return 0

    inserted = 0
    for code in CANONICAL_CODES:
        price_id = _env_price_for(code)
        if not price_id:
            log.warning(
                "billing.bootstrap.skip_missing_env",
                code=code,
                env_var=ENV_VAR_BY_CODE[code],
            )
            continue
        row = PlanConfig(
            id=uuid.uuid4(),
            code=code,
            stripe_price_id=price_id,
            stripe_product_id=None,
            eligibility=_ELIGIBILITY_BY_CODE[code],
            amount_cents=0,
            currency="USD",
            interval=_INTERVAL_BY_CODE[code],
            is_active=True,
            created_by_admin_id=None,
        )
        session.add(row)
        inserted += 1
    if inserted:
        await session.flush()
    log.info("billing.bootstrap.plan_configs_seeded", inserted=inserted)
    return inserted


async def assert_canonical_codes_resolve(session: AsyncSession) -> list[str]:
    """Re-export :func:`price_resolver.assert_all_codes_resolve` for clarity.

    Boot path uses this directly rather than going through the
    price-resolver module so logs are scoped to ``billing.bootstrap``.
    """
    gaps = await assert_all_codes_resolve(session)
    if gaps:
        log.warning("billing.bootstrap.startup_price_gap", unresolved=gaps)
    else:
        log.info("billing.bootstrap.all_codes_resolved")
    return gaps


__all__ = [
    "assert_canonical_codes_resolve",
    "seed_plan_configs_if_empty",
]
