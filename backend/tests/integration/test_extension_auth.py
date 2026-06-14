"""Unit tests for extension auth routes (Strategy B Phase 2).

These tests rely on the shared ``app_client`` fixture which auto-skips
when ``DATABASE_URL`` is not configured.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from tests.integration.test_auth import REGISTER_PAYLOAD


pytestmark = pytest.mark.integration


async def _register(client: AsyncClient, suffix: str = "") -> tuple[str, str]:
    """Register a user and return (access_token, email)."""
    email = f"ext-{suffix or 'test'}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["access_token"], email


@pytest.mark.asyncio
async def test_extension_login_returns_tokens_in_body(app_client: AsyncClient) -> None:
    _, email = await _register(app_client, "login")
    r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": email, "password": REGISTER_PAYLOAD["password"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["expires_in"] > 0
    assert body["user"]["email"] == email
    # Verify no Set-Cookie header (extension never uses cookies).
    assert "set-cookie" not in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_extension_login_invalid_credentials(app_client: AsyncClient) -> None:
    _, email = await _register(app_client, "badpw")
    r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": email, "password": "wrongpassword1"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_extension_login_unknown_email(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": "nobody@example.com", "password": "somepassword1"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_extension_refresh_rotates_token(app_client: AsyncClient) -> None:
    _, email = await _register(app_client, "refresh")
    login_r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": email, "password": REGISTER_PAYLOAD["password"]},
    )
    assert login_r.status_code == 200
    refresh_token = login_r.json()["refresh_token"]

    refresh_r = await app_client.post(
        "/api/auth/extension/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_r.status_code == 200, refresh_r.text
    new_body = refresh_r.json()
    assert "access_token" in new_body
    assert "refresh_token" in new_body
    # Rotated token must differ from the original.
    assert new_body["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_extension_refresh_reuse_is_rejected(app_client: AsyncClient) -> None:
    _, email = await _register(app_client, "reuse")
    login_r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": email, "password": REGISTER_PAYLOAD["password"]},
    )
    refresh_token = login_r.json()["refresh_token"]

    # First refresh — OK.
    await app_client.post(
        "/api/auth/extension/refresh",
        json={"refresh_token": refresh_token},
    )

    # Second refresh with the same (now-revoked) token.
    reuse_r = await app_client.post(
        "/api/auth/extension/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_r.status_code == 401
    assert reuse_r.json()["detail"]["code"] in (
        "refresh_token_reuse",
        "refresh_token_invalid",
    )


@pytest.mark.asyncio
async def test_extension_refresh_invalid_token(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/auth/extension/refresh",
        json={"refresh_token": "totally-invalid-token-value"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_extension_login_disabled_flag_returns_403(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When EXTENSION_AUTH_ENABLED=False, both routes return 403, not 404.

    The point is to fail closed without leaking endpoint existence to a
    scanner: a 404 would imply "no such route ever", a 403 implies "route
    exists but disabled". 403 is the honest answer.
    """
    monkeypatch.setattr(settings, "EXTENSION_AUTH_ENABLED", False)

    r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": "anyone@example.com", "password": "doesnotmatter1"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "extension_auth_disabled"

    r2 = await app_client.post(
        "/api/auth/extension/refresh",
        json={"refresh_token": "anything"},
    )
    assert r2.status_code == 403
    assert r2.json()["detail"]["code"] == "extension_auth_disabled"


@pytest.mark.asyncio
async def test_extension_login_rejects_totp_user(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """TOTP-enrolled users must not be issued tokens by the extension flow.

    The web flow returns a 2fa_challenge token which depends on cookies the
    extension cannot use. Phase 2 deliberately rejects TOTP users with a
    distinct error code so the popup can surface actionable guidance.
    """
    _, email = await _register(app_client, "totp")

    user = (
        await db_session.execute(
            User.__table__.select().where(User.email == email)
        )
    ).first()
    assert user is not None
    user_id = user.id

    # Flip has_totp directly. We do not exercise the full enrolment flow
    # because that requires a TOTP code round-trip; the route under test
    # only inspects user.has_totp.
    db_user = await db_session.get(User, user_id)
    assert db_user is not None
    db_user.has_totp = True
    await db_session.commit()

    r = await app_client.post(
        "/api/auth/extension/login",
        json={"email": email, "password": REGISTER_PAYLOAD["password"]},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "totp_not_supported_on_extension"
