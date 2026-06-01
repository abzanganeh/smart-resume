"""Nightly Stripe → PlanConfig drift detector (§7.8).

Run by EventBridge cron once per day:

1. Fetch every active price from Stripe (``stripe.Price.list(active=True)``).
2. For each canonical code in :data:`CANONICAL_CODES`, look up the
   matching ``PlanConfig`` row.  Compare ``stripe_price_id`` and
   ``amount_cents`` against what Stripe reports.
3. On any drift — Stripe price archived, amount changed without an
   admin action, missing PlanConfig row, or vice versa — write an
   :class:`AdminAuditLog` row with ``action='pricing_drift'`` and emit
   an ERROR-level structured log.  We deliberately do **not** mutate
   ``PlanConfig`` automatically; the admin must reconcile via the
   Step 35 UI.

The job is idempotent: each run inserts a fresh audit row that
captures the exact drift state at that moment, so re-running it the
next day produces a fresh log without rewriting history.

Notification scheduler Lambda routes ``stripe_price_sync`` events to
:func:`run_stripe_price_sync`.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import AdminAuditLog, PlanConfig
from app.services.billing.price_resolver import CANONICAL_CODES

log = structlog.get_logger("billing.price_sync")


@dataclass(frozen=True, slots=True)
class PriceDrift:
    """One drift finding emitted to the audit log + structured logs."""

    code: str | None
    kind: str  # "missing_plan_config" | "missing_stripe" | "price_id_changed" | "amount_changed" | "archived"
    db: dict[str, Any] = field(default_factory=dict)
    stripe: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PriceSyncResult:
    inspected: int
    drifts: list[PriceDrift]
    audit_ids: list[uuid.UUID]


def _configure_stripe() -> None:
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


async def _list_active_stripe_prices() -> list[dict[str, Any]]:
    """Page through Stripe and collect every active price as plain dicts."""
    if not settings.STRIPE_SECRET_KEY:
        return []
    _configure_stripe()

    def _list_one_page(starting_after: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"active": True, "limit": 100}
        if starting_after:
            kwargs["starting_after"] = starting_after
        return _to_dict(stripe.Price.list(**kwargs))

    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = await asyncio.to_thread(_list_one_page, cursor)
        page_data = page.get("data") or []
        items.extend(page_data)
        if not page.get("has_more") or not page_data:
            break
        cursor = page_data[-1].get("id")
        if not cursor:
            break
    return items


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return {"raw": str(obj)}


async def _all_active_plan_configs(
    session: AsyncSession,
) -> dict[str, PlanConfig]:
    """Return ``{code: PlanConfig}`` for currently-active rows."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(PlanConfig)
        .where(PlanConfig.is_active.is_(True))
        .where(PlanConfig.effective_from <= now)
        .where(
            (PlanConfig.effective_to.is_(None))
            | (PlanConfig.effective_to > now)
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.code: row for row in rows}


def _compare(
    *,
    code: str,
    plan: PlanConfig | None,
    stripe_price: dict[str, Any] | None,
) -> list[PriceDrift]:
    """Return zero or more drifts for one (code, plan, stripe_price)."""
    drifts: list[PriceDrift] = []

    if plan is None and stripe_price is None:
        # Missing in both layers — surface so admin can decide whether
        # to create the PlanConfig row or remove the canonical code.
        drifts.append(
            PriceDrift(
                code=code,
                kind="missing_plan_config",
                db={},
                stripe={},
            )
        )
        return drifts

    if plan is None and stripe_price is not None:
        drifts.append(
            PriceDrift(
                code=code,
                kind="missing_plan_config",
                db={},
                stripe={
                    "stripe_price_id": stripe_price.get("id"),
                    "amount_cents": stripe_price.get("unit_amount"),
                    "currency": stripe_price.get("currency"),
                },
            )
        )
        return drifts

    assert plan is not None  # for type narrowing

    if stripe_price is None:
        drifts.append(
            PriceDrift(
                code=code,
                kind="missing_stripe",
                db={
                    "stripe_price_id": plan.stripe_price_id,
                    "amount_cents": plan.amount_cents,
                },
                stripe={},
            )
        )
        return drifts

    if stripe_price.get("id") != plan.stripe_price_id:
        drifts.append(
            PriceDrift(
                code=code,
                kind="price_id_changed",
                db={"stripe_price_id": plan.stripe_price_id},
                stripe={"stripe_price_id": stripe_price.get("id")},
            )
        )

    stripe_amount = stripe_price.get("unit_amount")
    if (
        stripe_amount is not None
        and int(stripe_amount) != int(plan.amount_cents)
    ):
        drifts.append(
            PriceDrift(
                code=code,
                kind="amount_changed",
                db={"amount_cents": plan.amount_cents},
                stripe={"amount_cents": int(stripe_amount)},
            )
        )

    if not stripe_price.get("active", True):
        drifts.append(
            PriceDrift(
                code=code,
                kind="archived",
                db={"stripe_price_id": plan.stripe_price_id},
                stripe={"active": False},
            )
        )

    return drifts


def _find_orphans(
    *,
    plans_by_code: dict[str, PlanConfig],
    prices_by_id: dict[str, dict[str, Any]],
) -> list[PriceDrift]:
    """Surface PlanConfig rows whose Stripe price id is unknown.

    These are *not* one of the canonical codes (those are checked in
    the main loop) but represent misc rows admins may have added.
    """
    drifts: list[PriceDrift] = []
    canonical = set(CANONICAL_CODES)
    for code, plan in plans_by_code.items():
        if code in canonical:
            continue
        if plan.stripe_price_id not in prices_by_id:
            drifts.append(
                PriceDrift(
                    code=code,
                    kind="missing_stripe",
                    db={
                        "stripe_price_id": plan.stripe_price_id,
                        "amount_cents": plan.amount_cents,
                    },
                    stripe={},
                )
            )
    return drifts


async def _emit_drift_audit(
    session: AsyncSession,
    drifts: list[PriceDrift],
) -> uuid.UUID:
    """Write one consolidated AdminAuditLog row for the run.

    The ``after_json`` payload contains the full list of findings so an
    admin pulling the row up in the UI can see everything that drifted
    in one place; the structured log emits one ERROR per drift for
    metrics / dashboards.
    """
    audit_id = uuid.uuid4()
    row = AdminAuditLog(
        id=audit_id,
        actor_admin_id=None,
        action="pricing_drift",
        target_kind="plan_config",
        target_id="stripe_price_sync",
        before_json={},
        after_json={
            "drift_count": len(drifts),
            "drifts": [
                {
                    "code": d.code,
                    "kind": d.kind,
                    "db": d.db,
                    "stripe": d.stripe,
                }
                for d in drifts
            ],
        },
        ip="system:price_sync",
        user_agent="stripe_price_sync",
        request_id="",
    )
    session.add(row)
    await session.flush()
    return audit_id


async def run_stripe_price_sync(
    session: AsyncSession,
) -> PriceSyncResult:
    """Compare Stripe prices to PlanConfig and audit any drift (§7.8).

    Returns a :class:`PriceSyncResult` whose ``drifts`` list is empty
    when the deployment is in sync.  ``audit_ids`` is empty in that
    case as well — we only write an :class:`AdminAuditLog` row when
    drift is detected, so a healthy nightly run produces no audit
    noise.
    """
    plans_by_code = await _all_active_plan_configs(session)
    stripe_prices = await _list_active_stripe_prices()
    prices_by_id: dict[str, dict[str, Any]] = {
        str(p.get("id")): p for p in stripe_prices if p.get("id")
    }

    drifts: list[PriceDrift] = []
    for code in CANONICAL_CODES:
        plan = plans_by_code.get(code)
        stripe_price = (
            prices_by_id.get(plan.stripe_price_id) if plan else None
        )
        drifts.extend(_compare(code=code, plan=plan, stripe_price=stripe_price))

    drifts.extend(_find_orphans(plans_by_code=plans_by_code, prices_by_id=prices_by_id))

    audit_ids: list[uuid.UUID] = []
    if drifts:
        for d in drifts:
            log.error(
                "billing.price_sync.drift",
                code=d.code,
                kind=d.kind,
                db=d.db,
                stripe=d.stripe,
            )
        audit_ids.append(await _emit_drift_audit(session, drifts))

    log.info(
        "billing.price_sync.completed",
        canonical_codes=len(CANONICAL_CODES),
        active_stripe_prices=len(prices_by_id),
        drift_count=len(drifts),
    )
    return PriceSyncResult(
        inspected=len(prices_by_id),
        drifts=drifts,
        audit_ids=audit_ids,
    )


__all__ = [
    "PriceDrift",
    "PriceSyncResult",
    "run_stripe_price_sync",
]
