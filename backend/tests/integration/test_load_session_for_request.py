"""Integration tests for load_session_for_request edge cases."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserTier
from app.services.auth.tokens import create_access_token
from app.services.dashboard.session_cache import load_session_for_request
from app.services.session_store import create_session

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_load_session_for_request_none_redis_with_bearer_does_not_crash(
    db_session: AsyncSession,
) -> None:
    """Bearer restore path must not call resolve_bearer_user_id on a missing session."""
    user = User(
        id=uuid.uuid4(),
        email=f"load-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Load",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    missing_id = f"missing-{uuid.uuid4().hex[:12]}"
    token = create_access_token(str(user.id), session_id=uuid.uuid4())

    session = await load_session_for_request(
        db_session,
        session_id=missing_id,
        authorization=f"Bearer {token}",
    )
    assert session is None
