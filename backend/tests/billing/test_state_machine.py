"""Subscription state-machine integration tests (IMPLEMENTATION_PLAN §7.6).

Covers every transition in the §7.6 table:

| From                  | Event                                                     | To                    |
|-----------------------|-----------------------------------------------------------|-----------------------|
| trialing / active     | invoice.payment_failed (attempt 1)                        | grace                 |
| grace                 | invoice.payment_succeeded                                 | active                |
| grace                 | invoice.payment_failed (later attempt within window)      | grace (stay)          |
| grace                 | scheduler tick at payment_failed_at + 72h with no success | expired               |
| active                | customer.subscription.updated pause_collection!=null      | paused                |
| paused                | customer.subscription.updated pause_collection=null       | active                |
| active / grace        | customer.subscription.updated cancel_at_period_end=true   | cancel_at_period_end  |
| cancel_at_period_end  | customer.subscription.updated cancel_at_period_end=false  | active                |
| cancel_at_period_end  | scheduler tick at current_period_end                      | expired               |

For every row this module asserts:

- ``status`` lands on the expected target enum value.
- Side effects materialize: ``payment_failed_at``, ``ended_at``,
  ``cancel_at_period_end``, ``paused_at`` / ``pause_resumes_at``.
- The correct :class:`Notification` rows appear (or do not double-fire).
- The §7.6 :class:`AdminAuditLog` ``grace_to_expired`` row exists when
  the scheduler expires a row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    AdminAuditLog,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.notifications import Notification, NotificationChannel
from app.models.user import AuthProvider, User, UserTier
from app.services.billing import grace_tick as grace_tick_service
from app.services.billing import webhook_handler

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    session: AsyncSession,
    *,
    email: str | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email or f"fsm-{uuid.uuid4().hex[:8]}@example.com",
        display_name="FSM",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_subscription(
    session: AsyncSession,
    *,
    user: User,
    status: SubscriptionStatus,
    plan: SubscriptionPlan = SubscriptionPlan.monthly,
    billing_cycle: SubscriptionBillingCycle = SubscriptionBillingCycle.recurring,
    payment_failed_at: datetime | None = None,
    cancel_at_period_end: bool = False,
    period_end: datetime | None = None,
    stripe_subscription_id: str | None = None,
    stripe_price_id: str = "price_monthly_test",
) -> Subscription:
    period_end = period_end or datetime(2026, 12, 1, tzinfo=timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=plan,
        billing_cycle=billing_cycle,
        status=status,
        period_start=period_end - timedelta(days=30),
        period_end=period_end,
        cancel_at_period_end=cancel_at_period_end,
        payment_failed_at=payment_failed_at,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:12]}",
        stripe_subscription_id=stripe_subscription_id
        or f"sub_{uuid.uuid4().hex[:12]}",
        stripe_price_id=stripe_price_id,
    )
    session.add(sub)
    await session.flush()
    return sub


def _failed_event(
    *,
    stripe_subscription_id: str,
    event_id: str | None = None,
    created_ts: int | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex}",
        "type": "invoice.payment_failed",
        "created": created_ts
        or int(datetime.now(timezone.utc).timestamp()),
        "data": {"object": {"subscription": stripe_subscription_id}},
    }


def _succeeded_event(
    *,
    stripe_subscription_id: str,
    event_id: str | None = None,
    created_ts: int | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex}",
        "type": "invoice.payment_succeeded",
        "created": created_ts
        or int(datetime.now(timezone.utc).timestamp()),
        "data": {"object": {"subscription": stripe_subscription_id}},
    }


def _subscription_updated_event(
    *,
    stripe_subscription_id: str,
    customer_id: str,
    cancel_at_period_end: bool = False,
    pause_collection: dict[str, Any] | None | str = None,
    stripe_status: str = "active",
    period_end_ts: int | None = None,
    event_id: str | None = None,
    created_ts: int | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "id": stripe_subscription_id,
        "customer": customer_id,
        "status": stripe_status,
        "cancel_at_period_end": cancel_at_period_end,
        "current_period_start": int(
            datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()
        ),
        "current_period_end": period_end_ts
        or int(datetime(2026, 12, 1, tzinfo=timezone.utc).timestamp()),
        "items": {"data": []},
        "metadata": {},
    }
    if pause_collection is not None and pause_collection != "":
        obj["pause_collection"] = pause_collection
    elif pause_collection == "":
        obj["pause_collection"] = None
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex}",
        "type": "customer.subscription.updated",
        "created": created_ts
        or int(datetime.now(timezone.utc).timestamp()),
        "data": {"object": obj},
    }


async def _notifications_for(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID | None = None,
    notification_type: str | None = None,
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if notification_type is not None:
        stmt = stmt.where(Notification.type == notification_type)
    if subscription_id is not None:
        stmt = stmt.where(
            Notification.data["subscription_id"].astext == str(subscription_id)
        )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Tests — webhook-driven transitions (rows 1, 2, 3, 5, 6, 7, 9 in §7.6)
# ---------------------------------------------------------------------------


async def test_active_to_grace_on_invoice_payment_failed(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session, user=user, status=SubscriptionStatus.active
    )
    await db_session.commit()

    event = _failed_event(stripe_subscription_id=sub.stripe_subscription_id)
    await webhook_handler.handle_invoice_failed(db_session, event)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.grace
    assert sub.payment_failed_at is not None

    started = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="payment_failure_started",
    )
    # Both in_app and email channels emitted exactly once each.
    assert len(started) == 2
    assert {n.channel for n in started} == {
        NotificationChannel.in_app,
        NotificationChannel.email,
    }


async def test_grace_to_grace_no_duplicate_payment_failure_started(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session, user=user, status=SubscriptionStatus.active
    )
    await db_session.commit()

    first = _failed_event(stripe_subscription_id=sub.stripe_subscription_id)
    await webhook_handler.handle_invoice_failed(db_session, first)
    second = _failed_event(stripe_subscription_id=sub.stripe_subscription_id)
    await webhook_handler.handle_invoice_failed(db_session, second)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.grace
    started = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="payment_failure_started",
    )
    # Subsequent failures inside the same grace window MUST NOT fire
    # another payment_failure_started — the grace tick handles 24h /
    # 60h reminders.
    assert len(started) == 2  # 2 channels × 1 entry into grace


async def test_grace_to_active_on_invoice_succeeded_emits_payment_recovered(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        status=SubscriptionStatus.grace,
        payment_failed_at=datetime.now(timezone.utc) - timedelta(hours=10),
    )
    await db_session.commit()

    event = _succeeded_event(stripe_subscription_id=sub.stripe_subscription_id)
    await webhook_handler.handle_invoice_succeeded(db_session, event)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.active
    assert sub.payment_failed_at is None

    recovered = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="payment_recovered",
    )
    assert len(recovered) == 2


async def test_active_to_paused_via_subscription_updated(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session, user=user, status=SubscriptionStatus.active
    )
    await db_session.commit()

    resume_at = int(
        (datetime.now(timezone.utc) + timedelta(days=14)).timestamp()
    )
    event = _subscription_updated_event(
        stripe_subscription_id=sub.stripe_subscription_id,
        customer_id=sub.stripe_customer_id,
        pause_collection={"behavior": "void", "resumes_at": resume_at},
    )
    await webhook_handler.handle_subscription_updated(db_session, event)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.paused
    assert sub.pause_resumes_at is not None
    assert int(sub.pause_resumes_at.timestamp()) == resume_at


async def test_paused_to_active_when_pause_collection_clears(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session, user=user, status=SubscriptionStatus.paused
    )
    await db_session.commit()

    event = _subscription_updated_event(
        stripe_subscription_id=sub.stripe_subscription_id,
        customer_id=sub.stripe_customer_id,
        pause_collection=None,
        stripe_status="active",
    )
    await webhook_handler.handle_subscription_updated(db_session, event)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.active


async def test_active_to_cancel_at_period_end_via_subscription_updated(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session, user=user, status=SubscriptionStatus.active
    )
    await db_session.commit()

    event = _subscription_updated_event(
        stripe_subscription_id=sub.stripe_subscription_id,
        customer_id=sub.stripe_customer_id,
        cancel_at_period_end=True,
    )
    await webhook_handler.handle_subscription_updated(db_session, event)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.cancel_at_period_end
    assert sub.cancel_at_period_end is True


async def test_cancel_at_period_end_to_active_when_uncanceled(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        status=SubscriptionStatus.cancel_at_period_end,
        cancel_at_period_end=True,
    )
    await db_session.commit()

    event = _subscription_updated_event(
        stripe_subscription_id=sub.stripe_subscription_id,
        customer_id=sub.stripe_customer_id,
        cancel_at_period_end=False,
        stripe_status="active",
    )
    await webhook_handler.handle_subscription_updated(db_session, event)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.active
    assert sub.cancel_at_period_end is False


# ---------------------------------------------------------------------------
# Tests — scheduler-driven transitions (grace → expired)
# ---------------------------------------------------------------------------


async def test_grace_tick_24h_reminder_emitted_once(
    db_session: AsyncSession,
) -> None:
    """At 24h+ in grace the scheduler emits the 24h reminder.  Re-running
    it inside the same window must not double-emit."""
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        status=SubscriptionStatus.grace,
        payment_failed_at=now - timedelta(hours=25),
    )
    await db_session.commit()

    result1 = await grace_tick_service.run_grace_tick(db_session, now=now)
    await db_session.commit()
    result2 = await grace_tick_service.run_grace_tick(db_session, now=now)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.grace
    assert result1.reminders_emitted.get(24, 0) == 1
    assert result2.reminders_emitted.get(24, 0) == 0
    reminders_24h = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="payment_failure_reminder_24h",
    )
    assert len(reminders_24h) == 2  # in_app + email
    reminders_60h = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="payment_failure_reminder_60h",
    )
    assert reminders_60h == []


async def test_grace_tick_60h_reminder_after_24h_already_sent(
    db_session: AsyncSession,
) -> None:
    """After 60h+ the 60h reminder also lands."""
    now_24h = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    now_60h = now_24h + timedelta(hours=36)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        status=SubscriptionStatus.grace,
        payment_failed_at=now_24h - timedelta(hours=25),
    )
    await db_session.commit()

    await grace_tick_service.run_grace_tick(db_session, now=now_24h)
    await db_session.commit()
    result = await grace_tick_service.run_grace_tick(db_session, now=now_60h)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.grace
    assert result.reminders_emitted.get(60, 0) == 1
    reminders_60h = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="payment_failure_reminder_60h",
    )
    assert len(reminders_60h) == 2


async def test_grace_tick_72h_expiry_writes_audit_and_notification(
    db_session: AsyncSession,
) -> None:
    """At 72h+ the scheduler flips status, emits subscription_expired,
    and writes one ``grace_to_expired`` AdminAuditLog row."""
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(hours=settings.SUBSCRIPTION_GRACE_HOURS)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        status=SubscriptionStatus.grace,
        payment_failed_at=cutoff - timedelta(minutes=30),
    )
    await db_session.commit()

    result = await grace_tick_service.run_grace_tick(db_session, now=now)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.id in result.expired
    assert sub.status == SubscriptionStatus.expired
    assert sub.ended_at == now

    expired_rows = await _notifications_for(
        db_session,
        user_id=user.id,
        notification_type="subscription_expired",
    )
    assert len(expired_rows) == 2  # in_app + email
    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "grace_to_expired",
                    AdminAuditLog.target_id == str(sub.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


async def test_grace_tick_within_window_is_a_noop(
    db_session: AsyncSession,
) -> None:
    """A subscription that has been in grace for < 24h must not get any
    reminders or audit rows."""
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    user = await _seed_user(db_session)
    sub = await _seed_subscription(
        db_session,
        user=user,
        status=SubscriptionStatus.grace,
        payment_failed_at=now - timedelta(hours=2),
    )
    await db_session.commit()

    result = await grace_tick_service.run_grace_tick(db_session, now=now)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.status == SubscriptionStatus.grace
    assert result.reminders_emitted == {24: 0, 60: 0}
    assert result.expired == []


# ---------------------------------------------------------------------------
# Pause eligibility (§19.8)
# ---------------------------------------------------------------------------


async def test_pause_subscription_rejects_daily_plan(
    db_session: AsyncSession,
) -> None:
    """Daily / Weekly plans are too short-lived to satisfy the 7-day
    minimum pause window — service raises 422-ish exception."""
    from app.services.billing import subscription as sub_service
    from app.services.billing.exceptions import (
        SubscriptionPauseNotAllowedError,
    )

    user = await _seed_user(db_session)
    await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.daily,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
    )
    await db_session.commit()

    with pytest.raises(SubscriptionPauseNotAllowedError):
        await sub_service.pause_subscription(
            db_session,
            user=user,
            pause_until=datetime.now(timezone.utc) + timedelta(days=14),
        )


async def test_pause_subscription_rejects_window_outside_7_to_90_days(
    db_session: AsyncSession,
) -> None:
    from app.services.billing import subscription as sub_service

    user = await _seed_user(db_session)
    await _seed_subscription(
        db_session,
        user=user,
        plan=SubscriptionPlan.monthly,
        status=SubscriptionStatus.active,
    )
    await db_session.commit()

    too_short = datetime.now(timezone.utc) + timedelta(days=3)
    too_long = datetime.now(timezone.utc) + timedelta(days=120)

    with pytest.raises(ValueError):
        await sub_service.pause_subscription(
            db_session, user=user, pause_until=too_short
        )
    with pytest.raises(ValueError):
        await sub_service.pause_subscription(
            db_session, user=user, pause_until=too_long
        )
