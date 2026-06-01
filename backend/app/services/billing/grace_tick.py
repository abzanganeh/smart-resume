"""Grace-period scheduler tick — 24h / 60h reminders + 72h expiry (§7.6).

Per IMPLEMENTATION_PLAN §7.6 the day-0 ``payment_failure_started``
notification fires inside the ``invoice.payment_failed`` webhook; this
module owns everything that happens *after* that initial event:

- 24h reminder (``payment_failure_reminder_24h``) emitted when a
  subscription has been in ``grace`` for ≥ 24 hours and the row hasn't
  already received this reminder.
- 60h reminder (``payment_failure_reminder_60h``) emitted when a
  subscription has been in ``grace`` for ≥ 60 hours.
- 72h expiry: row transitions to ``expired``, ``ended_at`` is set,
  and a ``subscription_expired`` notification + ``AdminAuditLog`` row
  are written inside the same transaction.

Idempotency: each reminder type is keyed by
``(user_id, subscription_id, type)`` so re-running the tick within
the same window doesn't double-emit.  The 72h expiry path is
naturally idempotent because the WHERE clause excludes already
``expired`` rows.

EventBridge fires this tick every 15 minutes (Step 21 / Step 37
provisioning); the notification scheduler Lambda also routes a
``grace_tick`` event to :func:`run_grace_tick`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import AdminAuditLog, Subscription, SubscriptionStatus
from app.models.notifications import Notification, NotificationChannel
from app.services.notifications.factory import build_notification

log = structlog.get_logger("billing.grace_tick")


# Default reminder offsets (hours since payment_failed_at).  Kept as
# module-level constants so tests can monkeypatch them rather than
# changing settings.
REMINDER_HOURS: tuple[int, ...] = (24, 60)


@dataclass(frozen=True, slots=True)
class GraceTickResult:
    inspected: int
    expired: list[uuid.UUID]
    reminders_emitted: dict[int, int] = field(default_factory=dict)

    @property
    def reminders_total(self) -> int:
        return sum(self.reminders_emitted.values())


async def _has_reminder(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
    notification_type: str,
) -> bool:
    """Return True when this user already has the reminder logged.

    Treat both ``in_app`` and ``email`` rows as the same logical
    reminder so re-emission is suppressed regardless of which channel
    landed first.
    """
    stmt = (
        select(Notification.id)
        .where(Notification.user_id == user_id)
        .where(Notification.type == notification_type)
        .where(
            Notification.data["subscription_id"].astext
            == str(subscription_id)
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def _emit_reminder(
    session: AsyncSession,
    *,
    sub: Subscription,
    hours: int,
    now_dt: datetime,
) -> bool:
    """Emit the 24h or 60h reminder once.  Returns True when emitted."""
    notification_type = f"payment_failure_reminder_{hours}h"
    if await _has_reminder(
        session,
        user_id=sub.user_id,
        subscription_id=sub.id,
        notification_type=notification_type,
    ):
        return False

    payload = {
        "subscription_id": str(sub.id),
        "stripe_subscription_id": sub.stripe_subscription_id,
        "hours_in_grace": hours,
        "payment_failed_at": (
            sub.payment_failed_at.isoformat()
            if sub.payment_failed_at
            else None
        ),
        "url": "/billing",
    }
    title = f"Reminder: payment failed {hours} hours ago"
    body = (
        "Your subscription is still in the 72-hour grace window.  "
        "Please update your card to avoid losing access."
    )
    for channel in (NotificationChannel.in_app, NotificationChannel.email):
        session.add(
            build_notification(
                user_id=sub.user_id,
                type=notification_type,
                channel=channel,
                category="payment",
                title=title,
                body=body,
                data=payload,
                scheduled_at=now_dt,
            )
        )
    log.info(
        "billing.grace_tick.reminder_emitted",
        subscription_id=str(sub.id),
        user_id=str(sub.user_id),
        hours_in_grace=hours,
    )
    return True


def _seconds_in_grace(sub: Subscription, now_dt: datetime) -> float:
    if sub.payment_failed_at is None:
        return 0.0
    return (now_dt - sub.payment_failed_at).total_seconds()


async def run_grace_tick(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> GraceTickResult:
    """Drive the 24h / 60h / 72h §7.6 timeline forward.

    Runs in a single transaction so reminders + the eventual flip to
    ``expired`` are atomic with the audit row write.  Idempotent on
    re-run because:

    1. Reminders are keyed by ``(user_id, subscription_id, type)`` and
       the existence check skips already-emitted rows.
    2. The 72h expiry SELECT excludes ``status != 'grace'`` rows, so
       a second tick within the same minute finds nothing to do.
    """
    now_dt = now or datetime.now(timezone.utc)
    grace_window = timedelta(hours=settings.SUBSCRIPTION_GRACE_HOURS)
    expiry_cutoff = now_dt - grace_window

    # Single SELECT covers both reminder candidates and expiry
    # candidates.  We filter in Python so the same tick emits a 60h
    # reminder *and* expires the row when the cron lags.
    stmt = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.grace)
        .where(Subscription.payment_failed_at.is_not(None))
        .with_for_update(skip_locked=True)
    )
    rows = (await session.execute(stmt)).scalars().all()

    expired: list[uuid.UUID] = []
    reminders_emitted: dict[int, int] = {h: 0 for h in REMINDER_HOURS}

    for sub in rows:
        # Defensive double-check: another worker may have transitioned
        # this row in a concurrent tick that beat ``with_for_update``.
        if sub.status != SubscriptionStatus.grace:
            continue

        elapsed_seconds = _seconds_in_grace(sub, now_dt)

        # Reminders are emitted in chronological order; we always
        # check both so a tick that misses 24h still catches 60h.
        for hours in REMINDER_HOURS:
            threshold_seconds = hours * 3600
            within_expiry = elapsed_seconds < grace_window.total_seconds()
            if elapsed_seconds < threshold_seconds:
                continue
            if not within_expiry:
                # The expiry path below owns the final notification;
                # don't double-emit a reminder when the row is about
                # to flip to expired in the same transaction.
                continue
            if await _emit_reminder(
                session,
                sub=sub,
                hours=hours,
                now_dt=now_dt,
            ):
                reminders_emitted[hours] += 1

        # 72h expiry path.
        if (
            sub.payment_failed_at is not None
            and sub.payment_failed_at <= expiry_cutoff
        ):
            sub.status = SubscriptionStatus.expired
            sub.ended_at = now_dt
            sub.updated_at = now_dt
            expired.append(sub.id)
            session.add(
                build_notification(
                    user_id=sub.user_id,
                    type="subscription_expired",
                    channel=NotificationChannel.in_app,
                    category="subscription",
                    title="Your subscription has expired",
                    body=(
                        "Your grace period ended without a successful "
                        "payment.  New paid actions are blocked."
                    ),
                    data={
                        "subscription_id": str(sub.id),
                        "reason": "grace_window_elapsed",
                        "payment_failed_at": (
                            sub.payment_failed_at.isoformat()
                            if sub.payment_failed_at
                            else None
                        ),
                        "url": "/billing",
                    },
                )
            )
            session.add(
                build_notification(
                    user_id=sub.user_id,
                    type="subscription_expired",
                    channel=NotificationChannel.email,
                    category="subscription",
                    title="Your subscription has expired",
                    body=(
                        "Your grace period ended without a successful "
                        "payment.  New paid actions are blocked."
                    ),
                    data={
                        "subscription_id": str(sub.id),
                        "reason": "grace_window_elapsed",
                        "url": "/billing",
                    },
                )
            )
            session.add(
                AdminAuditLog(
                    id=uuid.uuid4(),
                    actor_admin_id=None,
                    action="grace_to_expired",
                    target_kind="subscription",
                    target_id=str(sub.id),
                    before_json={"status": SubscriptionStatus.grace.value},
                    after_json={"status": SubscriptionStatus.expired.value},
                    ip="system:grace_tick",
                    user_agent="subscriptions_grace_tick",
                    request_id="",
                )
            )
            log.info(
                "billing.grace_tick.expired",
                subscription_id=str(sub.id),
                user_id=str(sub.user_id),
                payment_failed_at=(
                    sub.payment_failed_at.isoformat()
                    if sub.payment_failed_at
                    else None
                ),
                grace_hours=settings.SUBSCRIPTION_GRACE_HOURS,
            )

    if expired or any(reminders_emitted.values()):
        await session.flush()

    log.info(
        "billing.grace_tick.completed",
        inspected=len(rows),
        expired=len(expired),
        reminders=reminders_emitted,
        cutoff=expiry_cutoff.isoformat(),
    )
    return GraceTickResult(
        inspected=len(rows),
        expired=expired,
        reminders_emitted=reminders_emitted,
    )


__all__ = ["GraceTickResult", "REMINDER_HOURS", "run_grace_tick"]
