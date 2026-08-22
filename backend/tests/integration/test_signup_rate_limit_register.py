"""Register enforces signup IP rate limits."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserTier
from app.services.auth.signup_fingerprint import hash_signup_device_fingerprint
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _seed_recent_signups(
    db_session: AsyncSession,
    *,
    signup_ip: str,
    fp_hash: str,
    count: int,
) -> None:
    now = datetime.now(timezone.utc)
    for _ in range(count):
        user = User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4().hex[:10]}@example.com",
            email_canonical=f"{uuid.uuid4().hex[:10]}@example.com",
            display_name="Rate",
            auth_provider=AuthProvider.email,
            password_hash="hash",
            tier=UserTier.free,
            signup_ip=signup_ip,
            signup_device_fingerprint_hash=fp_hash,
            accepted_tos_version="2026-06",
            created_at=now - timedelta(hours=2),
        )
        db_session.add(user)
    await db_session.flush()


@pytest.mark.asyncio
async def test_register_returns_rate_limit_when_ip_device_cap_hit(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.auth.signup_rate_limit.settings.SIGNUP_IP_DEVICE_DAILY_LIMIT",
        3,
    )
    monkeypatch.setattr(
        "app.services.auth.signup_rate_limit.settings.SIGNUP_IP_DAILY_LIMIT",
        15,
    )
    fp_raw = "deadbeef" * 4
    fp_hash = hash_signup_device_fingerprint(fp_raw)
    await _seed_recent_signups(
        db_session,
        signup_ip="testclient",
        fp_hash=fp_hash,
        count=3,
    )
    await db_session.commit()

    payload = {
        **REGISTER_PAYLOAD,
        "email": "rate-limit@example.com",
        "device_fingerprint": fp_raw,
    }
    resp = await app_client.post("/api/auth/register", json=payload)
    assert resp.status_code == 429, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "signup_rate_limited"
    assert "try again tomorrow" in detail["message"].lower()
