"""Tracker notification helpers (Step 29 → Step 31 scheduler)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Notification, NotificationChannel, NotificationStatus
from app.models.tracker import Application, ApplicationStatus


def _company(app: Application) -> str:
    return app.jd_company or "the company"


async def emit_status_change_notifications(
    session: AsyncSession,
    *,
    app: Application,
    old_status: ApplicationStatus,
    new_status: ApplicationStatus,
) -> None:
    if old_status == new_status:
        return

    company = _company(app)
    base_payload = {
        "application_id": str(app.id),
        "company": company,
        "title": app.jd_title,
        "old_status": old_status.value,
        "new_status": new_status.value,
    }

    if new_status == ApplicationStatus.offer:
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=app.user_id,
                type="application_offer_congrats",
                channel=NotificationChannel.in_app,
                status=NotificationStatus.pending,
                payload={
                    **base_payload,
                    "headline": f"Congratulations! Log your offer details for {company}",
                },
            )
        )
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=app.user_id,
                type="application_offer_congrats",
                channel=NotificationChannel.email,
                status=NotificationStatus.pending,
                payload={
                    **base_payload,
                    "headline": f"Congratulations! Log your offer details for {company}",
                },
            )
        )
        return

    if new_status == ApplicationStatus.applied:
        scheduled = datetime.now(timezone.utc)
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=app.user_id,
                type="application_follow_up_idle",
                channel=NotificationChannel.in_app,
                status=NotificationStatus.pending,
                scheduled_at=scheduled,
                payload={
                    **base_payload,
                    "headline": f"Any updates on your application at {company}?",
                    "idle_days": 14,
                },
            )
        )


async def create_custom_reminder(
    session: AsyncSession,
    *,
    app: Application,
    scheduled_at: datetime,
    message: str,
) -> Notification:
    notification = Notification(
        id=uuid.uuid4(),
        user_id=app.user_id,
        type="application_custom_reminder",
        channel=NotificationChannel.in_app,
        status=NotificationStatus.pending,
        scheduled_at=scheduled_at,
        payload={
            "application_id": str(app.id),
            "company": _company(app),
            "title": app.jd_title,
            "headline": message,
        },
    )
    session.add(notification)
    await session.flush()
    return notification


async def schedule_follow_up_reminder(
    session: AsyncSession,
    *,
    app: Application,
    follow_up_date: datetime,
) -> None:
    session.add(
        Notification(
            id=uuid.uuid4(),
            user_id=app.user_id,
            type="application_follow_up",
            channel=NotificationChannel.in_app,
            status=NotificationStatus.pending,
            scheduled_at=follow_up_date,
            payload={
                "application_id": str(app.id),
                "company": _company(app),
                "title": app.jd_title,
                "headline": f"Time to follow up on your application at {_company(app)}",
            },
        )
    )
    session.add(
        Notification(
            id=uuid.uuid4(),
            user_id=app.user_id,
            type="application_follow_up",
            channel=NotificationChannel.email,
            status=NotificationStatus.pending,
            scheduled_at=follow_up_date,
            payload={
                "application_id": str(app.id),
                "company": _company(app),
                "title": app.jd_title,
                "headline": f"Time to follow up on your application at {_company(app)}",
            },
        )
    )
