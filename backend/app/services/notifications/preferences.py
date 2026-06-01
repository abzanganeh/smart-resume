"""Notification preference helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import (
    DEFAULT_EMAIL_CATEGORIES,
    DEFAULT_IN_APP_CATEGORIES,
    DigestMode,
    NotificationPreference,
)


async def get_or_create_preferences(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> NotificationPreference:
    row = (
        await session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = NotificationPreference(
        id=uuid.uuid4(),
        user_id=user_id,
        email_enabled_categories=list(DEFAULT_EMAIL_CATEGORIES),
        in_app_enabled_categories=list(DEFAULT_IN_APP_CATEGORIES),
        web_push_enabled=False,
        sms_enabled=False,
        digest_mode=DigestMode.off,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


def category_enabled(
    prefs: NotificationPreference,
    *,
    category: str,
    channel: str,
) -> bool:
    if channel == "email":
        return category in (prefs.email_enabled_categories or [])
    if channel == "in_app":
        return category in (prefs.in_app_enabled_categories or [])
    if channel == "web_push":
        return prefs.web_push_enabled
    if channel == "sms":
        return prefs.sms_enabled and prefs.sms_phone_verified_at is not None
    return True


__all__ = ["category_enabled", "get_or_create_preferences"]
