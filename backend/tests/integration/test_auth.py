"""End-to-end auth flow: register → login → me → refresh → logout → refresh-replay.

Verifies the contracts laid out in §18.2 + §8.2:

- ``/register`` issues access + refresh tokens, sets the refresh cookie,
  grants 6 free credits via a ``CreditTransaction`` row.
- ``/login`` and ``/me`` round-trip the bearer access token.
- ``/refresh`` rotates the refresh token (new cookie, new access JWT).
- ``/logout`` revokes the current refresh token.
- Replaying the original (now revoked) refresh token fails with 401
  ``refresh_token_reuse`` and revokes every still-active token for the user.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import (
    AuthAuditEvent,
    AuthAuditLog,
    CreditTransaction,
    CreditTransactionAction,
    RefreshToken,
    User,
)
from app.routers.auth import REFRESH_COOKIE_NAME

pytestmark = pytest.mark.integration


REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "password": "tr0ub4dor&3sandwich-eats-paint",
    "display_name": "Alice",
    "accepted_tos_version": "2026-06",
    "marketing_opt_in": False,
}


async def _register(client: AsyncClient) -> tuple[str, str]:
    """Register and return ``(access_token, refresh_cookie)``."""
    r = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert body["user"]["credit_balance"] == 6
    refresh_cookie = r.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh_cookie, "refresh cookie must be set on register"
    return body["access_token"], refresh_cookie


async def test_register_grants_six_credits_and_audit_row(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(app_client)

    user = (
        await db_session.execute(
            select(User).where(User.email == REGISTER_PAYLOAD["email"])
        )
    ).scalar_one()
    assert user.credit_balance == 6

    grants = (
        await db_session.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        )
    ).scalars().all()
    assert len(grants) == 1
    assert grants[0].amount == 6
    assert grants[0].action == CreditTransactionAction.registration_grant

    audit_rows = (
        await db_session.execute(
            select(AuthAuditLog).where(AuthAuditLog.user_id == user.id)
        )
    ).scalars().all()
    assert any(r.event == AuthAuditEvent.login_success for r in audit_rows)


async def test_register_rejects_weak_password(app_client: AsyncClient) -> None:
    payload = {**REGISTER_PAYLOAD, "password": "password12"}
    r = await app_client.post("/api/auth/register", json=payload)
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "weak_password"


async def test_register_rejects_duplicate_email(app_client: AsyncClient) -> None:
    await _register(app_client)
    r = await app_client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_already_registered"


async def test_full_login_refresh_logout_replay_flow(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(app_client)

    # /login
    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    assert r.status_code == 200, r.text
    access = r.json()["access_token"]
    refresh = r.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh

    # /me
    r = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["email"] == REGISTER_PAYLOAD["email"]
    assert me["has_totp"] is False

    # /refresh — rotates the cookie + access token
    r = await app_client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: refresh},
    )
    assert r.status_code == 200, r.text
    rotated_refresh = r.cookies.get(REFRESH_COOKIE_NAME)
    assert rotated_refresh
    assert rotated_refresh != refresh, "refresh token must rotate"
    new_access = r.json()["access_token"]
    assert new_access != access

    # /logout (with the rotated refresh cookie)
    r = await app_client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {new_access}"},
        cookies={REFRESH_COOKIE_NAME: rotated_refresh},
    )
    assert r.status_code == 200, r.text

    # Replay of the original refresh token (now revoked AND the chain
    # has already been logged out) — must fail with 401.
    r = await app_client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: refresh},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_token_reuse"

    # Reuse detection must have killed every still-active token for this user.
    rows = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
    ).scalars().all()
    assert rows == []


async def test_login_failure_count_records_audit_rows(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(app_client)
    for _ in range(3):
        r = await app_client.post(
            "/api/auth/login",
            json={"email": REGISTER_PAYLOAD["email"], "password": "wrong-attempt-123"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "invalid_credentials"

    user = (
        await db_session.execute(
            select(User).where(User.email == REGISTER_PAYLOAD["email"])
        )
    ).scalar_one()
    failures = (
        await db_session.execute(
            select(AuthAuditLog).where(
                AuthAuditLog.user_id == user.id,
                AuthAuditLog.event == AuthAuditEvent.login_failure,
            )
        )
    ).scalars().all()
    assert len(failures) == 3


async def test_me_requires_bearer_token(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/auth/me")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


async def test_password_reset_invalidates_all_refresh_tokens(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.services.auth.email import make_password_reset_token

    access, refresh = await _register(app_client)
    user = (
        await db_session.execute(
            select(User).where(User.email == REGISTER_PAYLOAD["email"])
        )
    ).scalar_one()
    reset_token = make_password_reset_token(user.id)

    new_pw = "9X!verbatim-marsupial^tetrahedron"
    r = await app_client.post(
        "/api/auth/password/reset",
        json={"token": reset_token, "new_password": new_pw},
    )
    assert r.status_code == 200, r.text

    # All refresh tokens for the user must be revoked.
    active = (
        await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    assert active == []

    # And the old refresh cookie no longer works.
    r = await app_client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: refresh},
    )
    assert r.status_code == 401

    # New password works.
    r = await app_client.post(
        "/api/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": new_pw},
    )
    assert r.status_code == 200, r.text
