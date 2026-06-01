"""Route notifications to channel adapters with retry/backoff."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
)
from app.models.user import User
from app.services.notifications.email_adapter import send_notification_email
from app.services.notifications.preferences import category_enabled, get_or_create_preferences
from app.services.notifications.push_adapter import send_to_user_push_subscriptions
from app.services.notifications.sms_adapter import send_notification_sms

log = structlog.get_logger("notifications.dispatcher")

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


async def _deliver_once(
    session: AsyncSession,
    notification: Notification,
    *,
    user: User,
) -> dict[str, Any]:
    channel = notification.channel
    prefs = await get_or_create_preferences(session, user.id)

    if channel == NotificationChannel.in_app:
        if not category_enabled(prefs, category=notification.category, channel="in_app"):
            return {"sent": False, "reason": "category_disabled"}
        return {"sent": True, "provider": "in_app"}

    if channel == NotificationChannel.email:
        return await send_notification_email(
            session, notification, user=user, prefs=prefs
        )

    if channel == NotificationChannel.web_push:
        if not prefs.web_push_enabled:
            return {"sent": False, "reason": "web_push_disabled"}
        return await send_to_user_push_subscriptions(session, notification, user=user)

    if channel == NotificationChannel.sms:
        return await send_notification_sms(session, notification, user=user)

    if channel == NotificationChannel.multi:
        results: dict[str, Any] = {}
        for ch in ("in_app", "email", "web_push", "sms"):
            if category_enabled(prefs, category=notification.category, channel=ch):
                sub = Notification(
                    id=notification.id,
                    user_id=notification.user_id,
                    type=notification.type,
                    category=notification.category,
                    channel=NotificationChannel(ch),
                    title=notification.title,
                    body=notification.body,
                    data=notification.data,
                )
                results[ch] = await _deliver_once(session, sub, user=user)
        any_sent = any(r.get("sent") for r in results.values())
        return {"sent": any_sent, "channels": results}

    return {"sent": False, "reason": f"unknown_channel:{channel}"}


async def dispatch_notification(
    session: AsyncSession,
    notification: Notification,
) -> Notification:
    """Deliver a single notification with exponential backoff (3 attempts)."""
    user = (
        await session.execute(select(User).where(User.id == notification.user_id))
    ).scalar_one_or_none()
    if user is None:
        notification.delivery_status = NotificationDeliveryStatus.failed
        notification.error = "user_not_found"
        await session.flush()
        return notification

    if notification.channel == NotificationChannel.in_app:
        notification.sent_at = datetime.now(timezone.utc)
        notification.delivery_status = NotificationDeliveryStatus.delivered
        await session.flush()
        return notification

    last_error: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = await _deliver_once(session, notification, user=user)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            result = {"sent": False, "error": last_error}

        if result.get("sent"):
            notification.sent_at = datetime.now(timezone.utc)
            notification.delivery_status = NotificationDeliveryStatus.sent
            notification.error = None
            await session.flush()
            log.info(
                "notifications.dispatch.ok",
                notification_id=str(notification.id),
                channel=notification.channel.value,
                attempt=attempt,
            )
            return notification

        last_error = result.get("error") or result.get("reason") or "delivery_failed"
        if attempt < _MAX_ATTEMPTS:
            delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            await asyncio.sleep(delay)

    notification.delivery_status = NotificationDeliveryStatus.failed
    notification.error = last_error
    await session.flush()
    log.warning(
        "notifications.dispatch.failed",
        notification_id=str(notification.id),
        channel=notification.channel.value,
        error=last_error,
    )
    return notification


__all__ = ["dispatch_notification"]
