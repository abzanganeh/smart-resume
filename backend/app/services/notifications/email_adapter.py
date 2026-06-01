"""Resend email delivery for notifications."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notifications import Notification, NotificationPreference
from app.models.user import User
from app.services.notifications.preferences import category_enabled, get_or_create_preferences

log = structlog.get_logger("notifications.email")

_UNSUBSCRIBE_CATEGORIES_PARAM = "categories"


def _wrap_html(inner: str) -> str:
    return (
        '<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:#111;'
        'max-width:560px;margin:0 auto;padding:24px">'
        f"{inner}"
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0"/>'
        '<p style="font-size:11px;color:#9ca3af">Smart Resume — '
        "automated message, please do not reply.</p>"
        "</div>"
    )


def unsubscribe_link(user_id: uuid.UUID, category: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    qs = urlencode(
        {
            "user": str(user_id),
            _UNSUBSCRIBE_CATEGORIES_PARAM: category,
        }
    )
    return f"{base}/settings/notifications?{qs}"


async def send_notification_email(
    session: AsyncSession,
    notification: Notification,
    *,
    user: User,
    prefs: NotificationPreference | None = None,
) -> dict[str, Any]:
    if user.email_bounced_at is not None:
        return {"sent": False, "reason": "email_bounced"}

    prefs = prefs or await get_or_create_preferences(session, user.id)
    if not category_enabled(prefs, category=notification.category, channel="email"):
        return {"sent": False, "reason": "category_disabled"}

    deep_link = (notification.data or {}).get("url") or (
        f"{settings.FRONTEND_BASE_URL.rstrip('/')}/notifications"
    )
    unsub = unsubscribe_link(user.id, notification.category)
    subject = notification.title or notification.type.replace("_", " ").title()
    body_text = (
        f"{notification.body}\n\n"
        f"View in app: {deep_link}\n\n"
        f"Manage notification preferences: {unsub}"
    )
    body_html = _wrap_html(
        f"<p>{notification.body}</p>"
        f'<p><a href="{deep_link}" '
        'style="display:inline-block;padding:10px 18px;background:#0d9488;'
        'color:#fff;text-decoration:none;border-radius:6px">View in app</a></p>'
        f'<p style="font-size:12px;color:#666">'
        f'<a href="{unsub}">Unsubscribe from {notification.category} emails</a></p>'
    )

    if not settings.RESEND_API_KEY:
        log.info(
            "notifications.email.skipped",
            to=user.email,
            subject=subject,
            preview=body_text[:200],
        )
        return {"sent": True, "provider": "dev-log"}

    try:
        import resend
    except ImportError as exc:  # pragma: no cover
        log.warning("notifications.email.resend_missing", error=str(exc))
        return {"sent": False, "provider": "missing"}

    resend.api_key = settings.RESEND_API_KEY

    def _do_send() -> Any:
        return resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": [user.email],
                "subject": subject,
                "text": body_text,
                "html": body_html,
            }
        )

    try:
        result = await asyncio.to_thread(_do_send)
    except Exception as exc:  # pragma: no cover
        log.error("notifications.email.failed", error=str(exc), user_id=str(user.id))
        return {"sent": False, "provider": "resend", "error": str(exc)}

    log.info("notifications.email.sent", to=user.email, subject=subject)
    return {"sent": True, "provider": "resend", "result": result}


async def handle_resend_bounce(
    session: AsyncSession,
    *,
    email: str,
    bounced_at: datetime | None = None,
) -> bool:
    """Mark user email as bounced (Resend webhook)."""
    ts = bounced_at or datetime.now(timezone.utc)
    result = await session.execute(
        update(User)
        .where(User.email == email)
        .values(email_bounced_at=ts)
    )
    if (result.rowcount or 0) == 0:
        return False
    await session.flush()
    log.info("notifications.email.bounced", email=email)
    return True


__all__ = ["handle_resend_bounce", "send_notification_email", "unsubscribe_link"]
