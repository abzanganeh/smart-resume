"""Unit tests for ``POST /api/subscriptions/llm-upgrade/checkout``.

Covers the §7.7 billing-cycle alignment rule: a yearly LLM add-on
requires a yearly base subscription cycle.

Cases:

1. Monthly base + ``better_yearly`` request → HTTP 409
   ``billing_cycle_mismatch``.
2. Yearly base + ``better_yearly`` request → HTTP 200 with a Stripe
   checkout URL.
3. Spec-canonical ``better_5pack`` is accepted and resolves to the
   internal ``better_pack`` price.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    PlanConfig,
    PlanConfigInterval,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import User

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture()
async def stripe_secret_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_xxx")


_REGISTER_BASE = {
    "password": "tr0ub4dor&3sandwich-eats-paint",
    "display_name": "Test User",
    "accepted_tos_version": "2026-06",
    "marketing_opt_in": False,
}


async def _register_user(
    client: AsyncClient, db_session: AsyncSession, *, email: str
) -> tuple[User, dict[str, str]]:
    payload = {**_REGISTER_BASE, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    access = r.json()["access_token"]
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    return user, {"Authorization": f"Bearer {access}"}


async def _seed_base_subscription(
    db_session: AsyncSession,
    *,
    user: User,
    cycle: SubscriptionBillingCycle,
) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=cycle,
        status=SubscriptionStatus.active,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        cancel_at_period_end=False,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
        stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
        stripe_price_id="price_monthly_base",
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


async def _seed_plan_config(
    db_session: AsyncSession, *, code: str, price_id: str
) -> None:
    db_session.add(
        PlanConfig(
            id=uuid.uuid4(),
            code=code,
            stripe_price_id=price_id,
            amount_cents=499,
            currency="USD",
            interval=PlanConfigInterval.month,
            is_active=True,
        )
    )
    await db_session.commit()


async def test_yearly_addon_with_monthly_base_returns_409(
    app_client: AsyncClient,
    db_session: AsyncSession,
    stripe_secret_set: None,
) -> None:
    user, headers = await _register_user(
        app_client, db_session, email="monthly@example.com"
    )
    await _seed_base_subscription(
        db_session, user=user, cycle=SubscriptionBillingCycle.recurring
    )
    await _seed_plan_config(
        db_session, code="better_yearly", price_id="price_better_yearly_test"
    )

    res = await app_client.post(
        "/api/subscriptions/llm-upgrade/checkout",
        headers=headers,
        json={
            "code": "better_yearly",
            "success_url": "https://app.test/success",
            "cancel_url": "https://app.test/cancel",
        },
    )
    assert res.status_code == 409, res.text
    body = res.json()
    detail = body.get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "billing_cycle_mismatch"


async def test_yearly_addon_with_yearly_base_succeeds(
    app_client: AsyncClient,
    db_session: AsyncSession,
    stripe_secret_set: None,
) -> None:
    user, headers = await _register_user(
        app_client, db_session, email="yearly@example.com"
    )
    await _seed_base_subscription(
        db_session, user=user, cycle=SubscriptionBillingCycle.yearly
    )
    await _seed_plan_config(
        db_session, code="better_yearly", price_id="price_better_yearly_test"
    )

    fake_checkout = {
        "id": "cs_fake_yearly_ok",
        "url": "https://checkout.stripe.com/c/cs_fake_yearly_ok",
    }
    with patch(
        "stripe.checkout.Session.create",
        return_value=fake_checkout,
    ):
        res = await app_client.post(
            "/api/subscriptions/llm-upgrade/checkout",
            headers=headers,
            json={
                "code": "better_yearly",
                "success_url": "https://app.test/success",
                "cancel_url": "https://app.test/cancel",
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"].startswith("https://checkout.stripe.com/")


async def test_canonical_better_5pack_alias_resolves_to_better_pack(
    app_client: AsyncClient,
    db_session: AsyncSession,
    stripe_secret_set: None,
) -> None:
    """Spec-canonical ``better_5pack`` (IMPLEMENTATION_PLAN §7.1) maps
    to the legacy internal ``better_pack`` PlanConfig row.
    """
    _user, headers = await _register_user(
        app_client, db_session, email="alias@example.com"
    )
    await _seed_plan_config(
        db_session, code="better_pack", price_id="price_better_pack_test"
    )

    fake_checkout = {
        "id": "cs_fake_alias",
        "url": "https://checkout.stripe.com/c/cs_fake_alias",
    }
    with patch(
        "stripe.checkout.Session.create",
        return_value=fake_checkout,
    ):
        res = await app_client.post(
            "/api/subscriptions/llm-upgrade/checkout",
            headers=headers,
            json={
                "code": "better_5pack",
                "success_url": "https://app.test/success",
                "cancel_url": "https://app.test/cancel",
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"].startswith("https://checkout.stripe.com/")
