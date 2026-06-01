"""Dispatch scheduled notification outbox rows (EventBridge hourly)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notification, NotificationDeliveryStatus
from app.services.notifications.dispatcher import dispatch_notification

log = structlog.get_logger("notifications.scheduler")


@dataclass(frozen=True, slots=True)
class DispatchBatchResult:
    inspected: int
    dispatched: int
    failed: int


async def dispatch_pending_notifications(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> DispatchBatchResult:
    """Process notifications ready for delivery."""
    now_dt = now or datetime.now(timezone.utc)
    stmt = (
        select(Notification)
        .where(Notification.delivery_status == NotificationDeliveryStatus.pending)
        .where(Notification.sent_at.is_(None))
        .where(
            or_(
                Notification.scheduled_at.is_(None),
                Notification.scheduled_at <= now_dt,
            )
        )
        .order_by(Notification.scheduled_at.asc().nullsfirst())
        .with_for_update(skip_locked=True)
    )
    rows = (await session.execute(stmt)).scalars().all()
    dispatched = 0
    failed = 0
    for row in rows:
        await dispatch_notification(session, row)
        if row.delivery_status == NotificationDeliveryStatus.failed:
            failed += 1
        else:
            dispatched += 1
    if rows:
        await session.flush()
    log.info(
        "notifications.scheduler.completed",
        inspected=len(rows),
        dispatched=dispatched,
        failed=failed,
    )
    return DispatchBatchResult(
        inspected=len(rows),
        dispatched=dispatched,
        failed=failed,
    )


__all__ = ["DispatchBatchResult", "dispatch_pending_notifications"]
