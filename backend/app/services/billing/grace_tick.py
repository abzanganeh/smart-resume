"""Grace-period tick — transitions stale grace rows to expired (§7.6).

EventBridge fires ``subscriptions_grace_tick`` every 15 minutes (Step 21
provisions the schedule).  Each tick calls :func:`run_grace_tick` which:

1. Selects subscriptions in ``status='grace'`` whose
   ``payment_failed_at + 72h <= now()``.
2. For each row: transitions to ``expired``, sets ``ended_at=now()``,
   inserts a notification placeholder (Step 31 will fan out delivery),
   and writes an :class:`AdminAuditLog`-equivalent log entry.
3. Commits.

Idempotent on re-run: the WHERE clause excludes rows whose status is
already ``expired``, so running the worker twice in rapid succession
does not double-count or double-notify.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import AdminAuditLog, Subscription, SubscriptionStatus
from app.models.notifications import NotificationChannel
from app.services.notifications.factory import build_notification

log = structlog.get_logger("billing.grace_tick")


@dataclass(frozen=True, slots=True)
class GraceTickResult:
    inspected: int
    expired: list[uuid.UUID]


async def run_grace_tick(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> GraceTickResult:
    """Move stale grace subscriptions to ``expired``.

    Returns the list of subscription IDs that flipped this run.  An
    empty list means there was nothing to do (idempotent on re-run).
    """
    now_dt = now or datetime.now(timezone.utc)
    cutoff = now_dt - timedelta(hours=settings.SUBSCRIPTION_GRACE_HOURS)

    stmt = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.grace)
        .where(Subscription.payment_failed_at.is_not(None))
        .where(Subscription.payment_failed_at <= cutoff)
        .with_for_update(skip_locked=True)
    )
    rows = (await session.execute(stmt)).scalars().all()

    expired: list[uuid.UUID] = []
    for sub in rows:
        # Defensive double-check: another worker may have already
        # transitioned this row in a concurrent tick.
        if sub.status != SubscriptionStatus.grace:
            continue
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
                body="Your grace period ended without a successful payment.",
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
                sub.payment_failed_at.isoformat() if sub.payment_failed_at else None
            ),
            grace_hours=settings.SUBSCRIPTION_GRACE_HOURS,
        )

    if expired:
        await session.flush()

    log.info(
        "billing.grace_tick.completed",
        inspected=len(rows),
        expired=len(expired),
        cutoff=cutoff.isoformat(),
    )
    return GraceTickResult(inspected=len(rows), expired=expired)


__all__ = ["GraceTickResult", "run_grace_tick"]
