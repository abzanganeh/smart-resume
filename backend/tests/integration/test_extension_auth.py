"""Unit tests for extension auth routes (Strategy B Phase 2).

These tests use the in-memory session store and override ``get_db`` so no
Postgres is required.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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
