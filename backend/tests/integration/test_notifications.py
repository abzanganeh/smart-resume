"""Integration tests for notification platform (Steps 31–32)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from pywebpush import WebPushException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationPreference,
    WebPushSubscription,
)
from app.models.user import AuthProvider, User
from app.services.notifications.dispatcher import dispatch_notification
from app.services.notifications.factory import build_notification
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {**REGISTER_PAYLOAD, "email": f"notif-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


async def test_dispatch_email_calls_resend_once(
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="email-dispatch@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Test",
    )
    db_session.add(user)
    await db_session.flush()

    note = build_notification(
        user_id=user.id,
        type="payment_recovered",
        channel=NotificationChannel.email,
        category="payment",
        title="Payment received",
        body="Thanks for your payment.",
    )
    db_session.add(note)
    await db_session.flush()

    mock_send = MagicMock(return_value={"id": "email_123"})
    with patch("resend.Emails.send", mock_send):
        with patch("app.services.notifications.email_adapter.settings") as cfg:
            cfg.RESEND_API_KEY = "re_test"
            cfg.RESEND_FROM_EMAIL = "noreply@test.com"
            cfg.FRONTEND_BASE_URL = "http://localhost:3000"
            await dispatch_notification(db_session, note)

    mock_send.assert_called_once()
    assert note.delivery_status == NotificationDeliveryStatus.sent
    assert note.sent_at is not None


async def test_dispatch_web_push_410_deletes_subscription_and_email_fallback(
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="push-fallback@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Test",
    )
    db_session.add(user)
    await db_session.flush()

    sub = WebPushSubscription(
        id=uuid.uuid4(),
        user_id=user.id,
        endpoint="https://push.example/gone",
        keys={"p256dh": "k", "auth": "a"},
    )
    db_session.add(sub)
    prefs = NotificationPreference(
        id=uuid.uuid4(),
        user_id=user.id,
        email_enabled_categories=["application_interview"],
        in_app_enabled_categories=[],
        web_push_enabled=True,
    )
    db_session.add(prefs)
    await db_session.flush()

    note = build_notification(
        user_id=user.id,
        type="interview_reminder_24h",
        channel=NotificationChannel.web_push,
        category="application_interview",
        title="Interview tomorrow",
        body="Prep for your interview.",
    )
    db_session.add(note)
    await db_session.flush()

    response = MagicMock()
    response.status_code = 410
    exc = WebPushException("gone", response=response)

    mock_email = AsyncMock(return_value={"sent": True, "provider": "resend"})
    with patch("app.services.notifications.dispatcher.asyncio.sleep", return_value=None):
        with patch("app.services.notifications.push_adapter.webpush", side_effect=exc):
            with patch(
                "app.services.notifications.push_adapter.send_notification_email",
                mock_email,
            ) as email_fn:
                with patch("app.services.notifications.push_adapter.settings") as cfg:
                    cfg.WEB_PUSH_VAPID_PRIVATE_KEY = "priv"
                    cfg.WEB_PUSH_VAPID_PUBLIC_KEY = "pub"
                    cfg.WEB_PUSH_VAPID_SUBJECT = "mailto:test@test.com"
                    await dispatch_notification(db_session, note)

    remaining = (
        await db_session.execute(
            select(WebPushSubscription).where(WebPushSubscription.user_id == user.id)
        )
    ).scalars().all()
    assert remaining == []
    email_fn.assert_called_once()
    assert note.delivery_status == NotificationDeliveryStatus.sent


async def test_sms_verify_flow(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    phone = "+15551234567"

    with patch(
        "app.services.notifications.sms_verify.send_verification_sms",
        return_value={"sent": True, "provider": "dev-log"},
    ):
        with patch("app.services.notifications.sms_verify._code", return_value="123456"):
            r = await app_client.post(
                "/api/notifications/sms/send-verification",
                json={"phone": phone},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert r.status_code == 200, r.text

    r = await app_client.post(
        "/api/notifications/sms/verify",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    prefs = (
        await db_session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
    ).scalar_one()
    assert prefs.sms_phone_verified_at is not None
    assert prefs.sms_phone == phone


async def test_unread_count_after_in_app_notification(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)

    db_session.add(
        build_notification(
            user_id=user_id,
            type="resume_build_complete",
            channel=NotificationChannel.in_app,
            category="resume",
            title="Resume ready",
            body="Your tailored resume is ready to review.",
        )
    )
    await db_session.commit()

    r = await app_client.get(
        "/api/notifications/unread-count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["count"] >= 1


async def test_notification_preferences_get_and_patch(
    app_client: AsyncClient,
) -> None:
    token, _user_id = await _register(app_client)
    headers = {"Authorization": f"Bearer {token}"}

    get_res = await app_client.get("/api/notifications/preferences", headers=headers)
    assert get_res.status_code == 200, get_res.text
    body = get_res.json()
    assert "email_enabled_categories" in body
    assert "payment" in body["email_enabled_categories"]

    patch_res = await app_client.patch(
        "/api/notifications/preferences",
        json={
            "email_enabled_categories": [
                c for c in body["email_enabled_categories"] if c != "payment"
            ],
        },
        headers=headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    updated = patch_res.json()
    assert "payment" not in updated["email_enabled_categories"]


async def test_resend_bounce_webhook_sets_email_bounced_at(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    _ = token
    user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    assert user.email_bounced_at is None

    r = await app_client.post(
        "/api/notifications/webhooks/resend",
        json={
            "type": "email.bounced",
            "data": {"email": user.email},
        },
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(user)
    assert user.email_bounced_at is not None
