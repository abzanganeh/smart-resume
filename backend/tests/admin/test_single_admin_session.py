"""Single active admin session — second 2FA login revokes prior token."""

from __future__ import annotations

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from tests.admin.conftest import DEFAULT_PASSWORD, make_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_ADMIN_HEADERS = {
    "User-Agent": "pytest",
    "Accept-Language": "en-US",
    "X-Forwarded-For": "127.0.0.1",
}


async def _login_and_verify(
    app_client: AsyncClient,
    *,
    email: str,
    password: str,
    totp_secret: str,
) -> str:
    login = await app_client.post(
        "/api/admin/auth/login",
        json={"email": email, "password": password},
        headers=_ADMIN_HEADERS,
    )
    assert login.status_code == 200, login.text
    challenge = login.json()["challenge_token"]
    code = pyotp.TOTP(totp_secret).now()
    verify = await app_client.post(
        "/api/admin/auth/2fa/verify",
        json={"challenge_token": challenge, "code": code},
        headers=_ADMIN_HEADERS,
    )
    assert verify.status_code == 200, verify.text
    return verify.json()["access_token"]


async def test_second_login_revokes_prior_session(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "single-session@example.com"
    admin, secret = await make_admin(
        db_session, email=email, role=AdminRole.super_admin
    )
    await db_session.commit()

    token_a = await _login_and_verify(
        app_client, email=email, password=DEFAULT_PASSWORD, totp_secret=secret
    )
    headers_a = {**_ADMIN_HEADERS, "Authorization": f"Bearer {token_a}"}

    token_b = await _login_and_verify(
        app_client, email=email, password=DEFAULT_PASSWORD, totp_secret=secret
    )
    headers_b = {**_ADMIN_HEADERS, "Authorization": f"Bearer {token_b}"}

    revoked = await app_client.get("/api/admin/llm/steps", headers=headers_a)
    assert revoked.status_code == 401
    assert revoked.json()["detail"]["code"] == "admin_session_revoked"

    active = await app_client.get("/api/admin/llm/steps", headers=headers_b)
    assert active.status_code == 200


async def test_failed_2fa_does_not_revoke_existing_session(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "failed-2fa@example.com"
    admin, secret = await make_admin(
        db_session, email=email, role=AdminRole.super_admin
    )
    await db_session.commit()

    token_a = await _login_and_verify(
        app_client, email=email, password=DEFAULT_PASSWORD, totp_secret=secret
    )
    headers_a = {**_ADMIN_HEADERS, "Authorization": f"Bearer {token_a}"}

    login = await app_client.post(
        "/api/admin/auth/login",
        json={"email": email, "password": DEFAULT_PASSWORD},
        headers=_ADMIN_HEADERS,
    )
    challenge = login.json()["challenge_token"]
    bad_verify = await app_client.post(
        "/api/admin/auth/2fa/verify",
        json={"challenge_token": challenge, "code": "000000"},
        headers=_ADMIN_HEADERS,
    )
    assert bad_verify.status_code == 401

    still_active = await app_client.get("/api/admin/llm/steps", headers=headers_a)
    assert still_active.status_code == 200


async def test_revoke_is_scoped_to_same_admin_only(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin_a, secret_a = await make_admin(
        db_session, email="admin-a@example.com", role=AdminRole.super_admin
    )
    admin_b, secret_b = await make_admin(
        db_session, email="admin-b@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()

    token_b = await _login_and_verify(
        app_client,
        email="admin-b@example.com",
        password=DEFAULT_PASSWORD,
        totp_secret=secret_b,
    )
    headers_b = {**_ADMIN_HEADERS, "Authorization": f"Bearer {token_b}"}

    await _login_and_verify(
        app_client,
        email="admin-a@example.com",
        password=DEFAULT_PASSWORD,
        totp_secret=secret_a,
    )

    other_admin_still_active = await app_client.get(
        "/api/admin/llm/steps", headers=headers_b
    )
    assert other_admin_still_active.status_code == 200
