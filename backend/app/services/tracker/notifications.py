"""Tracker notification helpers (Step 29 → Step 31 scheduler)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notification, NotificationChannel
from app.models.tracker import Application, ApplicationStatus
from app.services.notifications.factory import build_notification


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
        "url": f"/tracker/{app.id}",
    }

    if new_status == ApplicationStatus.offer:
        headline = f"Congratulations! Log your offer details for {company}"
        session.add(
            build_notification(
                user_id=app.user_id,
                type="application_offer_congrats",
                channel=NotificationChannel.in_app,
                category="application_offer",
                title=headline,
                data={**base_payload, "headline": headline},
            )
        )
        session.add(
            build_notification(
                user_id=app.user_id,
                type="application_offer_congrats",
                channel=NotificationChannel.email,
                category="application_offer",
                title=headline,
                data={**base_payload, "headline": headline},
            )
        )
        return

    if new_status == ApplicationStatus.applied:
        scheduled = datetime.now(timezone.utc)
        headline = f"Any updates on your application at {company}?"
        session.add(
            build_notification(
                user_id=app.user_id,
                type="application_follow_up_idle",
                channel=NotificationChannel.in_app,
                category="application_nudge",
                title=headline,
                scheduled_at=scheduled,
                data={**base_payload, "headline": headline, "idle_days": 14},
            )
        )


async def create_custom_reminder(
    session: AsyncSession,
    *,
    app: Application,
    scheduled_at: datetime,
    message: str,
) -> Notification:
    notification = build_notification(
        user_id=app.user_id,
        type="application_custom_reminder",
        channel=NotificationChannel.in_app,
        category="application_follow_up",
        title=message,
        scheduled_at=scheduled_at,
        data={
            "application_id": str(app.id),
            "company": _company(app),
            "title": app.jd_title,
            "headline": message,
            "url": f"/tracker/{app.id}",
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
    headline = f"Time to follow up on your application at {_company(app)}"
    payload = {
        "application_id": str(app.id),
        "company": _company(app),
        "title": app.jd_title,
        "headline": headline,
        "url": f"/tracker/{app.id}",
    }
    session.add(
        build_notification(
            user_id=app.user_id,
            type="application_follow_up",
            channel=NotificationChannel.in_app,
            category="application_follow_up",
            title=headline,
            scheduled_at=follow_up_date,
            data=payload,
        )
    )
    session.add(
        build_notification(
            user_id=app.user_id,
            type="application_follow_up",
            channel=NotificationChannel.email,
            category="application_follow_up",
            title=headline,
            scheduled_at=follow_up_date,
            data=payload,
        )
    )
