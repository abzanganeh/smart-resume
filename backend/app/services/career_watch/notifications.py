"""Career Watch notification delivery (in-app + email/push outbox)."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import CareerAlert, CareerAlertStatus, CareerJobCache
from app.models.notifications import NotificationChannel
from app.services.notifications.factory import build_notification

log = structlog.get_logger("career_watch.notifications")


async def emit_career_watch_alert(session: AsyncSession, alert: CareerAlert) -> bool:
    """Create in-app notification and mark alert sent."""
    job = await session.get(CareerJobCache, alert.career_job_cache_id)
    if job is None:
        alert.status = CareerAlertStatus.expired
        await session.flush()
        return False

    title = f"New role: {job.title}"
    body = alert.match_reason or "A watched company posted a matching role."
    notification = build_notification(
        user_id=alert.user_id,
        type="career_watch_match",
        channel=NotificationChannel.in_app,
        title=title,
        body=body,
        category="job_alerts",
        data={
            "career_alert_id": str(alert.id),
            "career_job_cache_id": str(job.id),
            "apply_url": job.apply_url,
            "company_job_title": job.title,
        },
    )
    session.add(notification)
    email_notification = build_notification(
        user_id=alert.user_id,
        type="career_watch_match",
        channel=NotificationChannel.email,
        title=title,
        body=f"{body}\n\nApply: {job.apply_url}",
        category="job_alerts",
        data=notification.data,
    )
    session.add(email_notification)
    push_notification = build_notification(
        user_id=alert.user_id,
        type="career_watch_match",
        channel=NotificationChannel.web_push,
        title=title,
        body=body,
        category="job_alerts",
        data=notification.data,
    )
    session.add(push_notification)
    alert.status = CareerAlertStatus.sent
    alert.notified_at = datetime.now(timezone.utc)
    await session.flush()
    log.info(
        "career_watch_alert_sent",
        alert_id=str(alert.id),
        user_id=str(alert.user_id),
    )
    return True


async def dismiss_alert(
    session: AsyncSession,
    *,
    user_id,
    alert_id,
) -> CareerAlert:
    alert = (
        await session.execute(
            select(CareerAlert)
            .where(CareerAlert.id == alert_id)
            .where(CareerAlert.user_id == user_id)
        )
    ).scalar_one_or_none()
    if alert is None:
        raise LookupError("alert not found")
    alert.status = CareerAlertStatus.dismissed
    await session.flush()
    return alert


__all__ = ["dismiss_alert", "emit_career_watch_alert"]
