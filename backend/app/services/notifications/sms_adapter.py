"""Twilio SMS delivery — interview reminders only."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notifications import Notification
from app.models.user import User
from app.services.notifications.preferences import get_or_create_preferences

log = structlog.get_logger("notifications.sms")

INTERVIEW_TYPES = frozenset(
    {
        "interview_reminder_24h",
        "interview_reminder_1h",
        "application_interview_reminder",
    }
)


async def send_notification_sms(
    session: AsyncSession,
    notification: Notification,
    *,
    user: User,
) -> dict[str, Any]:
    if notification.type not in INTERVIEW_TYPES and not notification.type.startswith(
        "interview_"
    ):
        return {"sent": False, "reason": "sms_not_allowed_for_type"}

    prefs = await get_or_create_preferences(session, user.id)
    if not prefs.sms_enabled or prefs.sms_phone_verified_at is None:
        return {"sent": False, "reason": "sms_not_verified"}
    if not prefs.sms_phone:
        return {"sent": False, "reason": "sms_phone_missing"}

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        log.info(
            "notifications.sms.skipped",
            phone=prefs.sms_phone,
            preview=(notification.body or "")[:120],
        )
        return {"sent": True, "provider": "dev-log"}

    try:
        from twilio.rest import Client
    except ImportError as exc:  # pragma: no cover
        log.warning("notifications.sms.twilio_missing", error=str(exc))
        return {"sent": False, "provider": "missing"}

    body = notification.body or notification.title
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def _send() -> Any:
        return client.messages.create(
            body=body[:1600],
            from_=settings.TWILIO_FROM_NUMBER,
            to=prefs.sms_phone,
        )

    try:
        result = await asyncio.to_thread(_send)
    except Exception as exc:  # pragma: no cover
        log.error("notifications.sms.failed", error=str(exc))
        return {"sent": False, "error": str(exc)}

    log.info("notifications.sms.sent", phone=prefs.sms_phone)
    return {"sent": True, "provider": "twilio", "sid": getattr(result, "sid", None)}


__all__ = ["send_notification_sms"]
