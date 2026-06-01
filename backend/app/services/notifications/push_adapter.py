"""Web push delivery via pywebpush + VAPID."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notifications import Notification, WebPushSubscription
from app.models.user import User
from app.services.notifications.email_adapter import send_notification_email
from app.services.notifications.preferences import get_or_create_preferences

log = structlog.get_logger("notifications.push")

GONE_STATUS_CODES = {404, 410}


async def send_notification_push(
    session: AsyncSession,
    notification: Notification,
    *,
    user: User,
    subscription: WebPushSubscription,
) -> dict[str, Any]:
    if not settings.WEB_PUSH_VAPID_PRIVATE_KEY or not settings.WEB_PUSH_VAPID_PUBLIC_KEY:
        log.info("notifications.push.skipped", reason="vapid_not_configured")
        return {"sent": False, "reason": "vapid_not_configured"}

    payload = json.dumps(
        {
            "title": notification.title,
            "body": notification.body,
            "url": (notification.data or {}).get("url", "/notifications"),
            "tag": notification.type,
            "notification_id": str(notification.id),
        }
    )
    sub_info = {
        "endpoint": subscription.endpoint,
        "keys": subscription.keys,
    }
    vapid_claims = {"sub": settings.WEB_PUSH_VAPID_SUBJECT}

    def _do_push() -> None:
        webpush(
            subscription_info=sub_info,
            data=payload,
            vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
            vapid_claims=vapid_claims,
        )

    try:
        await asyncio.to_thread(_do_push)
    except WebPushException as exc:
        status = getattr(exc, "response", None)
        code = status.status_code if status is not None else None
        if code in GONE_STATUS_CODES:
            await session.execute(
                delete(WebPushSubscription).where(
                    WebPushSubscription.id == subscription.id
                )
            )
            await session.flush()
            log.info(
                "notifications.push.subscription_removed",
                endpoint=subscription.endpoint[:48],
                status_code=code,
            )
            prefs = await get_or_create_preferences(session, user.id)
            fallback = await send_notification_email(
                session, notification, user=user, prefs=prefs
            )
            return {
                "sent": bool(fallback.get("sent")),
                "reason": "subscription_gone",
                "email_fallback": fallback.get("sent", False),
            }
        log.error("notifications.push.failed", error=str(exc), code=code)
        return {"sent": False, "error": str(exc), "status_code": code}
    except Exception as exc:  # pragma: no cover
        log.error("notifications.push.failed", error=str(exc))
        return {"sent": False, "error": str(exc)}

    return {"sent": True, "provider": "webpush"}


async def send_to_user_push_subscriptions(
    session: AsyncSession,
    notification: Notification,
    *,
    user: User,
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(WebPushSubscription).where(WebPushSubscription.user_id == user.id)
        )
    ).scalars().all()
    if not rows:
        return {"sent": False, "reason": "no_subscriptions"}
    results = []
    any_sent = False
    for sub in rows:
        result = await send_notification_push(
            session, notification, user=user, subscription=sub
        )
        results.append(result)
        if result.get("sent"):
            any_sent = True
    return {"sent": any_sent, "results": results}


__all__ = ["send_notification_push", "send_to_user_push_subscriptions"]
