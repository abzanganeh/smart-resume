"""Stripe price-sync drift detector tests (§7.8)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    AdminAuditLog,
    PlanConfig,
    PlanConfigInterval,
)
from app.services.billing.price_sync import (
    PriceDrift,
    run_stripe_price_sync,
)

pytestmark = pytest.mark.integration


def _stripe_list_response(prices: list[dict[str, Any]]) -> Any:
    """Build a fake ``stripe.Price.list`` return value."""

    class _Resp:
        def __init__(self, data: list[dict[str, Any]]) -> None:
            self._data = data

        def to_dict_recursive(self) -> dict[str, Any]:
            return {"data": self._data, "has_more": False}

    return _Resp(prices)


async def _seed_plan(
    db_session: AsyncSession,
    *,
    code: str,
    stripe_price_id: str,
    amount_cents: int,
    interval: PlanConfigInterval = PlanConfigInterval.month,
) -> PlanConfig:
    plan = PlanConfig(
        id=uuid.uuid4(),
        code=code,
        stripe_price_id=stripe_price_id,
        amount_cents=amount_cents,
        currency="USD",
        interval=interval,
        is_active=True,
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


async def test_price_sync_no_drift_writes_no_audit(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every canonical PlanConfig matches Stripe, no audit row appears."""
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    # Seed every canonical code so the comparator sees no drift.
    canonical = {
        "daily": ("price_daily", 199),
        "weekly": ("price_weekly", 599),
        "monthly": ("price_monthly", 1999),
        "monthly_yearly": ("price_monthly_yearly", 18999),
        "better_pack": ("price_better_pack", 999),
        "better_monthly": ("price_better_monthly", 1499),
        "better_yearly": ("price_better_yearly", 13499),
        "best_per_resume": ("price_best_per_resume", 499),
        "best_monthly": ("price_best_monthly", 2499),
        "best_yearly": ("price_best_yearly", 22499),
    }
    for code, (price_id, amount) in canonical.items():
        await _seed_plan(
            db_session,
            code=code,
            stripe_price_id=price_id,
            amount_cents=amount,
        )
    await db_session.commit()

    fake_prices = [
        {"id": pid, "unit_amount": amt, "active": True, "currency": "usd"}
        for code, (pid, amt) in canonical.items()
    ]

    with patch(
        "app.services.billing.price_sync.stripe.Price.list",
        return_value=_stripe_list_response(fake_prices),
    ):
        result = await run_stripe_price_sync(db_session)

    await db_session.commit()
    assert result.drifts == []
    assert result.audit_ids == []
    audit_rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "pricing_drift"
                )
            )
        )
        .scalars()
        .all()
    )
    assert audit_rows == []


async def test_price_sync_amount_change_creates_pricing_drift_audit(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Stripe-side amount change is captured as ``amount_changed`` drift."""
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    # Seed only one canonical code so the result is deterministic — the
    # other canonical codes will surface as ``missing_plan_config``
    # which is also drift, but we focus the assertion on the targeted
    # row.
    await _seed_plan(
        db_session,
        code="monthly",
        stripe_price_id="price_monthly",
        amount_cents=1999,
    )
    await db_session.commit()

    # Stripe disagrees with the DB amount.
    fake_prices = [
        {
            "id": "price_monthly",
            "unit_amount": 2999,  # changed
            "active": True,
            "currency": "usd",
        }
    ]
    with patch(
        "app.services.billing.price_sync.stripe.Price.list",
        return_value=_stripe_list_response(fake_prices),
    ):
        result = await run_stripe_price_sync(db_session)

    await db_session.commit()

    drift_kinds = {d.kind for d in result.drifts if d.code == "monthly"}
    assert "amount_changed" in drift_kinds

    # PlanConfig was NOT mutated — admin must reconcile via the UI.
    plan = (
        await db_session.execute(
            select(PlanConfig).where(PlanConfig.code == "monthly")
        )
    ).scalar_one()
    assert plan.amount_cents == 1999

    audit_rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "pricing_drift"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    payload = audit_rows[0].after_json
    assert payload["drift_count"] >= 1


async def test_price_sync_archived_stripe_price_creates_drift(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    await _seed_plan(
        db_session,
        code="monthly",
        stripe_price_id="price_monthly",
        amount_cents=1999,
    )
    await db_session.commit()

    fake_prices = [
        {
            "id": "price_monthly",
            "unit_amount": 1999,
            "active": False,  # archived
            "currency": "usd",
        }
    ]
    with patch(
        "app.services.billing.price_sync.stripe.Price.list",
        return_value=_stripe_list_response(fake_prices),
    ):
        result = await run_stripe_price_sync(db_session)
    await db_session.commit()

    drifts_for_monthly = [d for d in result.drifts if d.code == "monthly"]
    assert any(d.kind == "archived" for d in drifts_for_monthly)
