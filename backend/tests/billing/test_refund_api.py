"""End-to-end test for the self-service 24h refund API path (Step 37).

Posts to ``POST /api/subscriptions/refund-request`` with
``within_24h=true`` and asserts the Stripe SDK is called once and a
:class:`RefundRecord` lands in the DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    RefundInitiator,
    RefundReason,
    RefundRecord,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


def _stripe_refund_response(refund_id: str) -> Any:
    class _Refund:
        def to_dict_recursive(self) -> dict[str, Any]:
            return {"id": refund_id, "status": "succeeded"}

    return _Refund()


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {
        **REGISTER_PAYLOAD,
        "email": f"refund-api-{uuid.uuid4().hex[:8]}@example.com",
    }
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


async def test_post_refund_request_within_24h_auto_approves_via_stripe(
    db_session: AsyncSession,
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    token, user_id = await _register(app_client)

    # Seed a subscription whose created_at is inside the 24h window.
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user_id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
        period_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        cancel_at_period_end=False,
        stripe_customer_id="cus_test",
        stripe_subscription_id=f"sub_{uuid.uuid4().hex[:12]}",
        stripe_price_id="price_monthly_test",
    )
    db_session.add(sub)
    await db_session.flush()
    sub.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "reason": "self_service_24h",
        "within_24h": True,
        "amount_usd": 19.99,
        "payment_intent": "pi_test",
        "note": "no usage in period",
    }
    with patch(
        "app.services.billing.refund.stripe.Refund.create",
        return_value=_stripe_refund_response("re_e2e"),
    ) as create_mock:
        resp = await app_client.post(
            "/api/subscriptions/refund-request",
            json=body,
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["auto_approved"] is True
    assert payload["stripe_refund_id"] == "re_e2e"
    create_mock.assert_called_once()

    record_id = uuid.UUID(payload["id"])
    row = (
        await db_session.execute(
            select(RefundRecord).where(RefundRecord.id == record_id)
        )
    ).scalar_one()
    assert row.reason == RefundReason.self_service_24h
    assert row.initiated_by == RefundInitiator.user
    assert row.stripe_refund_id == "re_e2e"
