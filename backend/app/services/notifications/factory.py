"""Factory for creating notification outbox rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
)


def build_notification(
    *,
    user_id: uuid.UUID,
    type: str,
    channel: NotificationChannel,
    title: str = "",
    body: str = "",
    category: str = "general",
    data: dict[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    notification_id: uuid.UUID | None = None,
) -> Notification:
    """Create a notification row; headline in legacy payload maps to title."""
    payload = data or {}
    resolved_title = title or payload.get("headline") or payload.get("title") or ""
    resolved_body = body or payload.get("body", "")
    return Notification(
        id=notification_id or uuid.uuid4(),
        user_id=user_id,
        type=type,
        category=category,
        channel=channel,
        title=resolved_title,
        body=resolved_body,
        data=payload,
        scheduled_at=scheduled_at,
        delivery_status=NotificationDeliveryStatus.pending,
    )


__all__ = ["build_notification"]
