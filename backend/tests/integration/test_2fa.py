"""TOTP 2FA enrollment + login challenge flows.

Mirrors the §18.2 contract:

- enroll → returns a base32 secret + provisioning URI; user.totp_secret
  is populated but ``has_totp`` is False until verify is called.
- verify (enrollment) → confirms a fresh TOTP code, emits 10 recovery
  codes (plaintext, once), stores them as bcrypt hashes.
- login when 2FA is on → issues a ``2fa_challenge`` token instead of a
  full access token.  Without TOTP code the user cannot complete login.
- /2fa/verify with the challenge token + a valid TOTP → completes login.
- /2fa/verify with no TOTP code (or wrong code) → 401.
- /2fa/disable → requires a current TOTP or recovery code.
"""

from __future__ import annotations

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.routers.auth import REFRESH_COOKIE_NAME
from app.services.auth.encryption import decrypt_bytes

pytestmark = pytest.mark.integration


REGISTER_PAYLOAD = {
    "email": "totp-user@example.com",
    "password": "tr0ub4dor&3sandwich-eats-paint",
    "display_name": "TOTP User",
    "accepted_tos_version": "2026-06",
    "marketing_opt_in": False,
}


async def _register_and_get_access(client: AsyncClient) -> str:
    r = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def _enroll_and_confirm(
    client: AsyncClient, access: str, db: AsyncSession, email: str
) -> tuple[str, list[str]]:
    """Walk through enroll → verify; return (secret_b32, recovery_codes)."""
    r = await client.post(
        "/api/auth/2fa/enroll",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    enroll = r.json()
    secret = enroll["secret"]
    assert secret and len(secret) >= 16
    assert enroll["provisioning_uri"].startswith("otpauth://totp/")

    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert user.totp_secret is not None
    assert user.has_totp is False
    assert decrypt_bytes(user.totp_secret).decode("utf-8") == secret
    assert user.totp_recovery_codes == []  # only minted after verify

    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/api/auth/2fa/verify",
        headers={"Authorization": f"Bearer {access}"},
        json={"code": code},
    )
    assert r.status_code == 200, r.text
    recovery_codes = r.json()["recovery_codes"]
    assert len(recovery_codes) == 10
    # Stored hashes must NOT be the plaintext codes.
    await db.refresh(user)
    assert len(user.totp_recovery_codes) == 10
    for plain in recovery_codes:
        assert plain not in user.totp_recovery_codes
    assert user.has_totp is True
    return secret, recovery_codes


async def test_enroll_verify_recovery_codes(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_get_access(app_client)
    secret, codes = await _enroll_and_confirm(
        app_client, access, db_session, REGISTER_PAYLOAD["email"]
    )
    assert len(set(codes)) == 10  # no duplicates


async def test_login_with_totp_completes_via_challenge(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_get_access(app_client)
    secret, _ = await _enroll_and_confirm(
        app_client, access, db_session, REGISTER_PAYLOAD["email"]
    )

    # Step 1: /login returns a 2FA challenge (no full access token).
    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    assert r.status_code == 401, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "2fa_required"
    challenge = detail["challenge_token"]
    # Cookies must NOT be set yet — login is half-complete.
    assert REFRESH_COOKIE_NAME not in r.cookies

    # Step 2: present challenge + TOTP → full access + refresh.
    code = pyotp.TOTP(secret).now()
    r = await app_client.post(
        "/api/auth/2fa/verify",
        json={"challenge_token": challenge, "code": code},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert body["user"]["has_totp"] is True
    assert r.cookies.get(REFRESH_COOKIE_NAME)


async def test_login_without_totp_after_enrollment_is_rejected(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The login route never returns a full access token when 2FA is enrolled."""
    access = await _register_and_get_access(app_client)
    await _enroll_and_confirm(
        app_client, access, db_session, REGISTER_PAYLOAD["email"]
    )

    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    # Either 401 with 2fa_required (no challenge supplied) — never 200.
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["code"] == "2fa_required"
    # No bearer token in the response.
    assert "access_token" not in r.json()


async def test_login_with_wrong_totp_is_rejected(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_get_access(app_client)
    await _enroll_and_confirm(
        app_client, access, db_session, REGISTER_PAYLOAD["email"]
    )

    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    challenge = r.json()["detail"]["challenge_token"]

    # Wrong code.
    r = await app_client.post(
        "/api/auth/2fa/verify",
        json={"challenge_token": challenge, "code": "000000"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tfa_invalid"


async def test_recovery_code_logs_in_and_is_single_use(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_get_access(app_client)
    _, codes = await _enroll_and_confirm(
        app_client, access, db_session, REGISTER_PAYLOAD["email"]
    )

    # Start login → get challenge.
    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    challenge = r.json()["detail"]["challenge_token"]

    # Use a recovery code instead of a TOTP code.
    chosen = codes[0]
    r = await app_client.post(
        "/api/auth/2fa/verify",
        json={"challenge_token": challenge, "recovery_code": chosen},
    )
    assert r.status_code == 200, r.text

    # Second attempt with the SAME code must fail (consumed).
    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    challenge2 = r.json()["detail"]["challenge_token"]
    r = await app_client.post(
        "/api/auth/2fa/verify",
        json={"challenge_token": challenge2, "recovery_code": chosen},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tfa_invalid"


async def test_disable_requires_valid_totp(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_get_access(app_client)
    secret, _ = await _enroll_and_confirm(
        app_client, access, db_session, REGISTER_PAYLOAD["email"]
    )

    # Re-login fully so we have a fresh access token.
    r = await app_client.post(
        "/api/auth/login",
        json={
            "email": REGISTER_PAYLOAD["email"],
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    challenge = r.json()["detail"]["challenge_token"]
    code = pyotp.TOTP(secret).now()
    r = await app_client.post(
        "/api/auth/2fa/verify",
        json={"challenge_token": challenge, "code": code},
    )
    access2 = r.json()["access_token"]

    # Wrong code → 401.
    r = await app_client.post(
        "/api/auth/2fa/disable",
        headers={"Authorization": f"Bearer {access2}"},
        json={"code": "000000"},
    )
    assert r.status_code == 401

    # Right code → 200 and TOTP is cleared.
    code = pyotp.TOTP(secret).now()
    r = await app_client.post(
        "/api/auth/2fa/disable",
        headers={"Authorization": f"Bearer {access2}"},
        json={"code": code},
    )
    assert r.status_code == 200, r.text

    user = (
        await db_session.execute(
            select(User).where(User.email == REGISTER_PAYLOAD["email"])
        )
    ).scalar_one()
    await db_session.refresh(user)
    assert user.totp_secret is None
    assert user.totp_recovery_codes == []


async def test_enroll_rejected_when_totp_already_enabled(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_get_access(app_client)
    await _enroll_and_confirm(app_client, access, db_session, REGISTER_PAYLOAD["email"])

    r = await app_client.post(
        "/api/auth/2fa/enroll",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tfa_already_enrolled"
