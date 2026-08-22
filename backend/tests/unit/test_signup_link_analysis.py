"""Signup link analysis tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserTier
from app.services.auth.signup_link_analysis import analyze_signup_links

pytestmark = pytest.mark.unit


async def _seed(
    db_session: AsyncSession,
    *,
    signup_ip: str,
    fp_hash: str,
    created_at: datetime,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        email_canonical=f"{uuid.uuid4().hex[:8]}@example.com",
        display_name="Link",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        signup_ip=signup_ip,
        signup_device_fingerprint_hash=fp_hash,
        accepted_tos_version="2026-06",
        created_at=created_at,
    )
    db_session.add(user)
    await db_session.flush()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fingerprint_cluster_flag_after_three_signups(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    ip = "198.51.100.77"
    fp = "shared-device-hash"
    for _ in range(3):
        await _seed(
            db_session,
            signup_ip=ip,
            fp_hash=fp,
            created_at=now - timedelta(hours=2),
        )

    flag = await analyze_signup_links(
        db_session,
        signup_ip=ip,
        device_fingerprint_hash=fp,
        now=now,
    )
    assert flag == "fingerprint_cluster"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ip_cluster_flag_after_ten_signups(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    ip = "198.51.100.88"
    for idx in range(10):
        await _seed(
            db_session,
            signup_ip=ip,
            fp_hash=f"device-{idx}",
            created_at=now - timedelta(hours=2),
        )

    flag = await analyze_signup_links(
        db_session,
        signup_ip=ip,
        device_fingerprint_hash="new-device-hash-value",
        now=now,
    )
    assert flag == "ip_cluster"
