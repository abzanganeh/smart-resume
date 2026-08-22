"""Concurrent auth session enforcement — one active session per user (Redis).

When a user logs in or registers on a new device, prior refresh tokens are
revoked and the active session id in Redis is replaced.  Stale access tokens
and refresh tokens must surface ``session_replaced`` (401).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserTier
from app.routers.auth import REFRESH_COOKIE_NAME
from app.services.auth import session as redis_session
from app.services.auth.exceptions import SessionReplacedError
from app.services.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    new_auth_session_id,
    rotate_refresh_token,
)
from app.services.auth.dependencies import get_current_user
from fastapi import HTTPException
from unittest.mock import MagicMock

pytestmark = pytest.mark.integration

REGISTER_PAYLOAD = {
    "email": "concurrent@example.com",
    "password": "tr0ub4dor&3sandwich-eats-paint",
    "display_name": "Concurrent User",
    "accepted_tos_version": "2026-06",
    "marketing_opt_in": False,
    "turnstile_token": "test-turnstile-token",
}


async def _register(client: AsyncClient) -> tuple[str, str]:
    r = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()
    refresh = r.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh
    return body["access_token"], refresh


async def _login(client: AsyncClient) -> tuple[str, str]:
    r = await client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    refresh = r.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh
    return body["access_token"], refresh


# ---------------------------------------------------------------------------
# session.py unit behaviour (in-memory fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_active_auth_session() -> None:
    redis_session._reset_for_tests()
    user_id = uuid.uuid4()
    session_id = new_auth_session_id()

    await redis_session.set_active_auth_session(user_id, session_id, ttl=3600)
    assert await redis_session.get_active_auth_session_id(user_id) == str(session_id)

    await redis_session.clear_active_auth_session(user_id)
    assert await redis_session.get_active_auth_session_id(user_id) is None


@pytest.mark.asyncio
async def test_bind_refresh_token_stores_auth_session_id() -> None:
    redis_session._reset_for_tests()
    user_id = uuid.uuid4()
    token_id = uuid.uuid4()
    auth_session_id = new_auth_session_id()

    await redis_session.bind_refresh_token_to_redis(
        token_id,
        user_id,
        "fp-1",
        ttl=3600,
        auth_session_id=auth_session_id,
    )
    meta = await redis_session.get_refresh_token_metadata(token_id)
    assert meta is not None
    assert meta["auth_session_id"] == str(auth_session_id)


@pytest.mark.asyncio
async def test_revoke_all_user_tokens_clears_active_session() -> None:
    redis_session._reset_for_tests()
    user_id = uuid.uuid4()
    session_id = new_auth_session_id()
    token_id = uuid.uuid4()

    await redis_session.set_active_auth_session(user_id, session_id, ttl=3600)
    await redis_session.bind_refresh_token_to_redis(
        token_id, user_id, "fp", ttl=3600, auth_session_id=session_id
    )

    count = await redis_session.revoke_all_user_tokens(user_id)
    assert count == 1
    assert await redis_session.get_refresh_token_metadata(token_id) is None


# ---------------------------------------------------------------------------
# access token sid claim
# ---------------------------------------------------------------------------


def test_access_token_carries_session_id_claim() -> None:
    user_id = uuid.uuid4()
    session_id = new_auth_session_id()
    token = create_access_token(user_id, session_id=session_id)
    claims = decode_access_token(token)
    assert claims["sid"] == str(session_id)


# ---------------------------------------------------------------------------
# HTTP + DB integration
# ---------------------------------------------------------------------------


async def test_second_login_invalidates_first_session(
    app_client: AsyncClient,
) -> None:
    first_access, first_refresh = await _register(app_client)
    second_access, second_refresh = await _login(app_client)

    assert first_refresh != second_refresh
    assert first_access != second_access

    r = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {first_access}"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "session_replaced"

    r = await app_client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: first_refresh},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "session_replaced"


async def test_refresh_within_same_session_succeeds(
    app_client: AsyncClient,
) -> None:
    _, refresh = await _register(app_client)

    r = await app_client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: refresh},
    )
    assert r.status_code == 200, r.text
    new_access = r.json()["access_token"]

    r = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert r.status_code == 200


async def test_get_current_user_rejects_stale_session_id(
    db_session: AsyncSession,
) -> None:
    redis_session._reset_for_tests()
    user = User(
        id=uuid.uuid4(),
        email="sid-check@example.com",
        display_name="Sid",
        auth_provider=AuthProvider.email,
        password_hash="$2b$12$placeholder.placeholder.placeholder.placeholder.placeholder",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()

    old_session = new_auth_session_id()
    new_session = new_auth_session_id()
    await redis_session.set_active_auth_session(
        user.id, new_session, ttl=3600
    )

    stale_token = create_access_token(user.id, session_id=old_session)
    request = MagicMock()
    request.state = MagicMock()

    from fastapi.security import HTTPAuthorizationCredentials

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=stale_token
    )

    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(request, credentials, db_session)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == {"code": "session_replaced"}


async def test_rotate_revoked_token_from_replaced_session_raises_session_replaced(
    db_session: AsyncSession,
) -> None:
    redis_session._reset_for_tests()
    user = User(
        id=uuid.uuid4(),
        email="rotate@example.com",
        display_name="Rotate",
        auth_provider=AuthProvider.email,
        password_hash="$2b$12$placeholder.placeholder.placeholder.placeholder.placeholder",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()

    old_session = new_auth_session_id()
    new_session = new_auth_session_id()
    issued = await create_refresh_token(
        db_session, user_id=user.id, device_fingerprint="fp"
    )
    await redis_session.bind_refresh_token_to_redis(
        issued.token_id,
        user.id,
        "fp",
        ttl=3600,
        auth_session_id=old_session,
    )

    # Simulate a new login elsewhere: revoke DB row + swap active session.
    issued.row.revoked_at = issued.row.issued_at
    await db_session.flush()
    await redis_session.revoke_all_user_tokens(user.id)
    await redis_session.set_active_auth_session(
        user.id, new_session, ttl=3600
    )

    with pytest.raises(SessionReplacedError):
        await rotate_refresh_token(
            db_session,
            token=issued.token,
            device_fingerprint="fp",
        )
