"""Notification platform routes (IMPLEMENTATION_PLAN §6 Notifications)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.limiter import limiter
from app.models.notifications import (
    DigestMode,
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationPreference,
    WebPushSubscription,
)
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.notifications.preferences import get_or_create_preferences
from app.services.notifications.sms_verify import (
    send_verification_sms,
    store_pending_code,
    verify_code,
)

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NotificationItem(BaseModel):
    id: uuid.UUID
    type: str
    category: str
    channel: str
    title: str
    body: str
    data: dict[str, Any]
    read_at: datetime | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    delivery_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int


class UnreadCountResponse(BaseModel):
    count: int


class PreferencesResponse(BaseModel):
    email_enabled_categories: list[str]
    in_app_enabled_categories: list[str]
    web_push_enabled: bool
    sms_enabled: bool
    sms_phone: str | None
    sms_phone_verified_at: datetime | None
    digest_mode: str

    model_config = {"from_attributes": True}


class PreferencesPatchRequest(BaseModel):
    email_enabled_categories: list[str] | None = None
    in_app_enabled_categories: list[str] | None = None
    web_push_enabled: bool | None = None
    sms_enabled: bool | None = None
    digest_mode: Literal["off", "daily"] | None = None


class WebPushSubscribeRequest(BaseModel):
    endpoint: str
    expiration_time: datetime | None = None
    keys: dict[str, str]
    user_agent: str = ""
    platform_hint: str = ""


class SmsSendVerificationRequest(BaseModel):
    phone: str = Field(..., min_length=8, max_length=32)


class SmsVerifyRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=8)


def _to_item(row: Notification) -> NotificationItem:
    return NotificationItem(
        id=row.id,
        type=row.type,
        category=row.category,
        channel=row.channel.value,
        title=row.title,
        body=row.body,
        data=row.data or {},
        read_at=row.read_at,
        scheduled_at=row.scheduled_at,
        sent_at=row.sent_at,
        delivery_status=row.delivery_status.value,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


@router.get("/api/notifications")
@limiter.limit("120/minute")
async def list_notifications(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    unread_only: bool = Query(False),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> NotificationListResponse:
    stmt = select(Notification).where(
        Notification.user_id == user.id,
        Notification.channel == NotificationChannel.in_app,
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if category:
        stmt = stmt.where(Notification.category == category)
    count_filters = [
        Notification.user_id == user.id,
        Notification.channel == NotificationChannel.in_app,
    ]
    if unread_only:
        count_filters.append(Notification.read_at.is_(None))
    if category:
        count_filters.append(Notification.category == category)
    total = (
        await db.execute(select(func.count()).where(*count_filters))
    ).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(desc(Notification.created_at)).limit(limit).offset(offset)
        )
    ).scalars().all()
    return NotificationListResponse(
        items=[_to_item(r) for r in rows],
        total=total,
    )


@router.get("/api/notifications/unread-count")
@limiter.limit("120/minute")
async def unread_count(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UnreadCountResponse:
    count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.channel == NotificationChannel.in_app,
                Notification.read_at.is_(None),
            )
        )
    ).scalar_one()
    return UnreadCountResponse(count=count)


@router.patch("/api/notifications/{notification_id}/read")
@limiter.limit("60/minute")
async def mark_read(
    request: Request,
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NotificationItem:
    row = (
        await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        await db.flush()
    return _to_item(row)


@router.patch("/api/notifications/read-all")
@limiter.limit("30/minute")
async def mark_all_read(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, int]:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.channel == NotificationChannel.in_app,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    return {"updated": result.rowcount}


@router.delete("/api/notifications/{notification_id}")
@limiter.limit("30/minute")
async def dismiss_notification(
    request: Request,
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    row = (
        await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.delete(row)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


@router.get("/api/notifications/preferences")
@limiter.limit("120/minute")
async def get_preferences(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PreferencesResponse:
    prefs = await get_or_create_preferences(db, user.id)
    return PreferencesResponse(
        email_enabled_categories=prefs.email_enabled_categories or [],
        in_app_enabled_categories=prefs.in_app_enabled_categories or [],
        web_push_enabled=prefs.web_push_enabled,
        sms_enabled=prefs.sms_enabled,
        sms_phone=prefs.sms_phone,
        sms_phone_verified_at=prefs.sms_phone_verified_at,
        digest_mode=prefs.digest_mode.value,
    )


@router.patch("/api/notifications/preferences")
@limiter.limit("30/minute")
async def patch_preferences(
    request: Request,
    body: PreferencesPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PreferencesResponse:
    prefs = await get_or_create_preferences(db, user.id)
    if body.email_enabled_categories is not None:
        prefs.email_enabled_categories = body.email_enabled_categories
    if body.in_app_enabled_categories is not None:
        prefs.in_app_enabled_categories = body.in_app_enabled_categories
    if body.web_push_enabled is not None:
        prefs.web_push_enabled = body.web_push_enabled
    if body.sms_enabled is not None:
        prefs.sms_enabled = body.sms_enabled
    if body.digest_mode is not None:
        prefs.digest_mode = DigestMode(body.digest_mode)
    prefs.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return await get_preferences(request, db, user)


# ---------------------------------------------------------------------------
# Web push
# ---------------------------------------------------------------------------


@router.post("/api/notifications/web-push/subscribe", status_code=200)
@limiter.limit("10/minute")
async def web_push_subscribe(
    request: Request,
    body: WebPushSubscribeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    existing = (
        await db.execute(
            select(WebPushSubscription).where(
                WebPushSubscription.user_id == user.id,
                WebPushSubscription.endpoint == body.endpoint,
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing:
        existing.keys = body.keys
        existing.expiration_time = body.expiration_time
        existing.user_agent = body.user_agent
        existing.platform_hint = body.platform_hint
        existing.updated_at = now
    else:
        db.add(
            WebPushSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                endpoint=body.endpoint,
                expiration_time=body.expiration_time,
                keys=body.keys,
                user_agent=body.user_agent,
                platform_hint=body.platform_hint,
                created_at=now,
                updated_at=now,
            )
        )
    prefs = await get_or_create_preferences(db, user.id)
    prefs.web_push_enabled = True
    prefs.updated_at = now
    await db.flush()
    return {"ok": True}


@router.delete("/api/notifications/web-push/subscribe")
@limiter.limit("10/minute")
async def web_push_unsubscribe(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    endpoint: str | None = Query(None),
) -> dict[str, bool]:
    stmt = delete(WebPushSubscription).where(WebPushSubscription.user_id == user.id)
    if endpoint:
        stmt = stmt.where(WebPushSubscription.endpoint == endpoint)
    await db.execute(stmt)
    if not endpoint:
        prefs = await get_or_create_preferences(db, user.id)
        prefs.web_push_enabled = False
        prefs.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"ok": True}


# ---------------------------------------------------------------------------
# SMS verification
# ---------------------------------------------------------------------------


@router.post("/api/notifications/sms/send-verification")
@limiter.limit("5/minute")
async def sms_send_verification(
    request: Request,
    body: SmsSendVerificationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    phone = body.phone.strip()
    if not phone.startswith("+"):
        raise HTTPException(status_code=422, detail="Phone must be E.164 (+...)")
    code = await store_pending_code(str(user.id), phone)
    await send_verification_sms(phone, code)
    prefs = await get_or_create_preferences(db, user.id)
    prefs.sms_phone = phone
    prefs.sms_phone_verified_at = None
    prefs.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"ok": True}


@router.post("/api/notifications/sms/verify")
@limiter.limit("5/minute")
async def sms_verify(
    request: Request,
    body: SmsVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    ok, phone = await verify_code(str(user.id), body.code)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    prefs = await get_or_create_preferences(db, user.id)
    if phone:
        prefs.sms_phone = phone
    prefs.sms_phone_verified_at = datetime.now(timezone.utc)
    prefs.sms_enabled = True
    prefs.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"ok": True, "verified": True}
