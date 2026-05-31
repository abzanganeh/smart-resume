"""Canonical ``code → stripe_price_id`` resolution per IMPLEMENTATION_PLAN §7.2.

Two-layer lookup:

1. ``plan_configs`` row where ``code = :code`` and the row is currently
   active (``is_active`` AND ``effective_from <= now() < coalesce(effective_to, infinity)``).
2. ``STRIPE_PRICE_<CODE_UPPER>`` env var (bootstrap / disaster-recovery
   only).
3. If neither resolves, raise :class:`PriceUnresolvedError` so the
   router can surface HTTP 503 ``price_unresolved``.

Reverse lookup (``stripe_price_id → code``) is used by webhook handlers
to identify which product was purchased.  When Stripe delivers a
``price_id`` not present in either layer we deliberately do not crash
the dispatcher — the webhook is parked in ``needs_review`` (§7.2).
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import PlanConfig
from app.services.billing.exceptions import PriceUnresolvedError

log = structlog.get_logger("billing.price_resolver")


# IMPLEMENTATION_PLAN §7.1 — canonical 10 codes the application addresses.
# Boot-time assertion (see ``app/main.py``) verifies all of them resolve.
CANONICAL_CODES: tuple[str, ...] = (
    "daily",
    "weekly",
    "monthly",
    "monthly_yearly",
    "better_pack",
    "better_monthly",
    "better_yearly",
    "best_per_resume",
    "best_monthly",
    "best_yearly",
)


# Human-readable code → env-var key.  ``code.upper()`` would also work
# but the explicit map prevents silent typos and lets ``monthly_yearly``
# map to ``STRIPE_PRICE_MONTHLY_YEARLY`` etc.
ENV_VAR_BY_CODE: dict[str, str] = {
    "daily": "STRIPE_PRICE_DAILY",
    "weekly": "STRIPE_PRICE_WEEKLY",
    "monthly": "STRIPE_PRICE_MONTHLY",
    "monthly_yearly": "STRIPE_PRICE_MONTHLY_YEARLY",
    "better_pack": "STRIPE_PRICE_BETTER_PACK",
    "better_monthly": "STRIPE_PRICE_BETTER_MONTHLY",
    "better_yearly": "STRIPE_PRICE_BETTER_YEARLY",
    "best_per_resume": "STRIPE_PRICE_BEST_PER_RESUME",
    "best_monthly": "STRIPE_PRICE_BEST_MONTHLY",
    "best_yearly": "STRIPE_PRICE_BEST_YEARLY",
}


def _env_price_for(code: str) -> str:
    env_key = ENV_VAR_BY_CODE.get(code, f"STRIPE_PRICE_{code.upper()}")
    return getattr(settings, env_key, "") or ""


async def resolve_price_id(session: AsyncSession, code: str) -> str:
    """Resolve the active stripe_price_id for ``code``.

    Order: PlanConfig (DB) → env var → :class:`PriceUnresolvedError`.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(PlanConfig.stripe_price_id)
        .where(PlanConfig.code == code)
        .where(PlanConfig.is_active.is_(True))
        .where(PlanConfig.effective_from <= now)
        .where(
            (PlanConfig.effective_to.is_(None)) | (PlanConfig.effective_to > now)
        )
        .order_by(PlanConfig.effective_from.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row:
        return row

    env_value = _env_price_for(code)
    if env_value:
        return env_value

    log.error(
        "billing.price_resolver.unresolved",
        code=code,
        env_var=ENV_VAR_BY_CODE.get(code, "<none>"),
    )
    raise PriceUnresolvedError(code)


async def reverse_lookup_code(
    session: AsyncSession, stripe_price_id: str
) -> str | None:
    """Return the canonical ``code`` for a Stripe price id, or None.

    Webhook handlers use this to figure out *what* the user bought.  A
    None return triggers ``stripe_webhook_event.status='needs_review'``
    rather than a crash or a silent grant (§7.2 hardening).
    """
    stmt = (
        select(PlanConfig.code)
        .where(PlanConfig.stripe_price_id == stripe_price_id)
        .where(PlanConfig.is_active.is_(True))
        .order_by(PlanConfig.effective_from.desc())
        .limit(1)
    )
    code = (await session.execute(stmt)).scalar_one_or_none()
    if code:
        return code
    # Env-var fallback — useful in CI / staging before PlanConfig seed runs.
    for candidate, env_key in ENV_VAR_BY_CODE.items():
        if getattr(settings, env_key, "") == stripe_price_id:
            return candidate
    return None


async def assert_all_codes_resolve(session: AsyncSession) -> list[str]:
    """Boot-time assertion that every canonical code resolves.

    Returns the list of *unresolved* codes.  An empty list means the
    deployment is healthy.  Callers (``app/main.py`` startup hook + CI
    staging gate) log a WARN per gap and may abort boot in production.
    """
    gaps: list[str] = []
    for code in CANONICAL_CODES:
        try:
            await resolve_price_id(session, code)
        except PriceUnresolvedError:
            gaps.append(code)
    if gaps:
        log.warning(
            "billing.price_resolver.startup_price_gap",
            unresolved=gaps,
        )
    return gaps


__all__ = [
    "CANONICAL_CODES",
    "ENV_VAR_BY_CODE",
    "assert_all_codes_resolve",
    "resolve_price_id",
    "reverse_lookup_code",
]
