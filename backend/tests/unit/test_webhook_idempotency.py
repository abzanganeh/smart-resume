"""Webhook idempotency — the same Stripe event delivered twice is a no-op.

Asserts the contract from IMPLEMENTATION_PLAN §7.4:

1. First delivery → row inserted, ``status=processed``, attempts=1.
2. Second delivery with the same ``event_id`` → returned 200 immediately
   without DB mutation; the row's ``processed_at`` does **not** change
   and no second :class:`CreditTransaction` row is written.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
import stripe
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    CreditKind,
    PlanConfig,
    PlanConfigInterval,
    StripeWebhookEvent,
    StripeWebhookStatus,
)
from app.models.user import (
    AuthProvider,
    CreditTransaction,
    User,
    UserTier,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture()
async def webhook_secret_set(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "whsec_test_idempotency"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    return secret


def _signed_headers(secret: str, body: bytes) -> dict[str, str]:
    """Build a Stripe-signature header using the SDK so verify passes."""
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signed_payload = f"{timestamp}.{body.decode()}"
    import hashlib
    import hmac as _hmac

    sig = _hmac.new(
        secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()
    return {"stripe-signature": f"t={timestamp},v1={sig}"}


async def _seed_user_and_plan(db_session: AsyncSession) -> tuple[User, str]:
    user = User(
        id=uuid.uuid4(),
        email="alice@example.com",
        display_name="Alice",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()

    plan = PlanConfig(
        id=uuid.uuid4(),
        code="better_pack",
        stripe_price_id="price_better_pack_test",
        amount_cents=499,
        currency="USD",
        interval=PlanConfigInterval.one_time,
        is_active=True,
    )
    db_session.add(plan)
    await db_session.commit()
    return user, plan.stripe_price_id


def _checkout_event(event_id: str, user_id: uuid.UUID, code: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_test_123",
                "customer": "cus_test_123",
                "client_reference_id": str(user_id),
                "metadata": {"user_id": str(user_id), "code": code},
            }
        },
    }


async def test_duplicate_webhook_delivery_is_noop(
    app_client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret_set: str,
) -> None:
    user, _ = await _seed_user_and_plan(db_session)
    event = _checkout_event(
        event_id="evt_idem_001", user_id=user.id, code="better_pack"
    )
    body = json.dumps(event).encode()
    headers = _signed_headers(webhook_secret_set, body)

    with patch.object(
        stripe.Webhook, "construct_event", return_value=event
    ):
        first = await app_client.post(
            "/api/webhooks/stripe", content=body, headers=headers
        )
    assert first.status_code == 200, first.text
    assert first.json() == {"received": True}

    # Snapshot DB state after the first call.
    rows_after_first = (
        await db_session.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        )
    ).scalars().all()
    assert len(rows_after_first) == 1, "first delivery should grant 5 better credits"
    assert rows_after_first[0].delta == 5
    assert rows_after_first[0].credit_kind == CreditKind.better
    assert rows_after_first[0].stripe_event_id == "evt_idem_001"

    webhook_row = (
        await db_session.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.event_id == "evt_idem_001"
            )
        )
    ).scalar_one()
    assert webhook_row.status == StripeWebhookStatus.processed
    first_processed_at = webhook_row.processed_at

    with patch.object(
        stripe.Webhook, "construct_event", return_value=event
    ):
        second = await app_client.post(
            "/api/webhooks/stripe", content=body, headers=headers
        )
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload.get("duplicate") is True

    # No additional credit transaction should have been written.
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.user_id == user.id)
        )
    ).scalar()
    assert count == 1, "duplicate webhook must not write a second ledger row"

    # Webhook row processed_at must be unchanged.
    refreshed = (
        await db_session.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.event_id == "evt_idem_001"
            )
        )
    ).scalar_one()
    assert refreshed.processed_at == first_processed_at
    assert refreshed.status == StripeWebhookStatus.processed
