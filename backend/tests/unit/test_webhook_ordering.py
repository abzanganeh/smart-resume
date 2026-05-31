"""Webhook ordering — older ``customer.subscription.updated`` events skip mutation.

Asserts the contract from IMPLEMENTATION_PLAN §7.4: when an event's
``event.created`` is *older* than the target subscription's
``last_event_created_at``, the handler marks the row processed without
applying the mutation and logs ``out_of_order_skip``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    PlanConfig,
    PlanConfigInterval,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.webhook_handler import dispatch

pytestmark = pytest.mark.integration


def _updated_event(
    *,
    event_id: str,
    stripe_subscription_id: str,
    created_at: datetime,
    new_status: str,
    cancel_at_period_end: bool = False,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "customer.subscription.updated",
        "created": int(created_at.timestamp()),
        "livemode": False,
        "data": {
            "object": {
                "id": stripe_subscription_id,
                "customer": "cus_x",
                "status": new_status,
                "cancel_at_period_end": cancel_at_period_end,
                "current_period_start": int(
                    datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()
                ),
                "current_period_end": int(
                    datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
                ),
                "trial_end": None,
                "items": {
                    "data": [{"price": {"id": "price_monthly_test"}}]
                },
            }
        },
    }


@pytest_asyncio.fixture()
async def seeded_subscription(db_session: AsyncSession) -> Subscription:
    user = User(
        id=uuid.uuid4(),
        email="bob@example.com",
        display_name="Bob",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
        period_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        cancel_at_period_end=False,
        stripe_customer_id="cus_x",
        stripe_subscription_id="sub_ordering_test",
        stripe_price_id="price_monthly_test",
        last_event_created_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(sub)
    db_session.add(
        PlanConfig(
            id=uuid.uuid4(),
            code="monthly",
            stripe_price_id="price_monthly_test",
            stripe_product_id="prod_monthly_test",
            eligibility="base_plan",
            amount_cents=1999,
            currency="USD",
            interval=PlanConfigInterval.month,
            is_active=True,
        )
    )
    await db_session.commit()
    return sub


async def test_older_event_is_skipped(
    db_session: AsyncSession, seeded_subscription: Subscription
) -> None:
    older = _updated_event(
        event_id="evt_ordering_older",
        stripe_subscription_id="sub_ordering_test",
        created_at=datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),  # before last_event
        new_status="canceled",
        cancel_at_period_end=True,
    )
    await dispatch(db_session, older)
    await db_session.flush()
    await db_session.refresh(seeded_subscription)

    # Status must remain ``active`` — the older event should not have
    # mutated the row even though it carries a state-changing payload.
    assert seeded_subscription.status == SubscriptionStatus.active
    assert seeded_subscription.cancel_at_period_end is False
    # The watermark must remain at the original value (the older
    # event did not advance it).
    assert seeded_subscription.last_event_created_at == datetime(
        2026, 5, 30, 12, 0, tzinfo=timezone.utc
    )


async def test_newer_event_applies(
    db_session: AsyncSession, seeded_subscription: Subscription
) -> None:
    newer = _updated_event(
        event_id="evt_ordering_newer",
        stripe_subscription_id="sub_ordering_test",
        created_at=datetime(2026, 5, 30, 13, 0, tzinfo=timezone.utc),
        new_status="active",
        cancel_at_period_end=True,
    )
    await dispatch(db_session, newer)
    await db_session.flush()
    await db_session.refresh(seeded_subscription)

    # ``cancel_at_period_end=True`` flips the status mapping per §7.6.
    assert seeded_subscription.status == SubscriptionStatus.cancel_at_period_end
    assert seeded_subscription.cancel_at_period_end is True
    assert seeded_subscription.last_event_created_at == datetime(
        2026, 5, 30, 13, 0, tzinfo=timezone.utc
    )
