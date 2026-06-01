"""Mandatory 2FA enforcement (IMPLEMENTATION_PLAN section 8.4.2).

Verifies that the credentials-only login path NEVER hands out an
``admin_session`` token; only ``admin_2fa_setup`` (when not yet
enrolled) or ``admin_challenge`` (when enrolled) tokens are returned.
A ``admin_2fa_setup`` token can only reach the ``/auth/2fa/enroll``
endpoint and not any RBAC-gated route.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from app.services.admin_auth import tokens as admin_tokens
from tests.admin.conftest import DEFAULT_PASSWORD, make_admin


@pytest.mark.asyncio
async def test_login_without_2fa_returns_setup_token(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="needs2fa@example.com",
        role=AdminRole.super_admin,
        enrolled_2fa=False,
        must_enroll_2fa=True,
    )
    await db_session.commit()

    resp = await app_client.post(
        "/api/admin/auth/login",
        json={"email": "needs2fa@example.com", "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next"] == "enroll_2fa"
    assert body["must_enroll_2fa"] is True
    assert "challenge_token" in body
    assert "access_token" not in body and "session_token" not in body

    # Setup token must NOT pass session decode
    with pytest.raises(admin_tokens.AdminTokenInvalid):
        await admin_tokens.decode_admin_session_token(
            body["challenge_token"],
            request_ip="127.0.0.1",
            request_ua_fingerprint=admin_tokens.make_ua_fingerprint("pytest", "en-US"),
        )


@pytest.mark.asyncio
async def test_login_with_2fa_enrolled_returns_challenge_token(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="enrolled@example.com",
        role=AdminRole.super_admin,
        enrolled_2fa=True,
    )
    await db_session.commit()

    resp = await app_client.post(
        "/api/admin/auth/login",
        json={"email": "enrolled@example.com", "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next"] == "verify_2fa"
    assert "challenge_token" in body
    assert "access_token" not in body


@pytest.mark.asyncio
async def test_setup_token_cannot_reach_rbac_routes(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="setup-only@example.com",
        role=AdminRole.super_admin,
        enrolled_2fa=False,
        must_enroll_2fa=True,
    )
    await db_session.commit()

    login = await app_client.post(
        "/api/admin/auth/login",
        json={"email": "setup-only@example.com", "password": DEFAULT_PASSWORD},
    )
    setup_token = login.json()["challenge_token"]

    # Try a few representative RBAC-gated endpoints with the setup
    # token in the Authorization header.  All must reject with 401.
    for path in ("/api/admin/users", "/api/admin/plans", "/api/admin/feature-flags"):
        r = await app_client.get(
            path, headers={"Authorization": f"Bearer {setup_token}"}
        )
        assert r.status_code == 401, (path, r.status_code, r.text)


@pytest.mark.asyncio
async def test_anonymous_admin_request_is_401(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/users")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_invalid_credentials_returns_401(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    await make_admin(
        db_session, email="x@example.com", role=AdminRole.admin, enrolled_2fa=True
    )
    await db_session.commit()

    resp = await app_client.post(
        "/api/admin/auth/login",
        json={"email": "x@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
