"""JWT issuance + refresh-token rotation with reuse detection.

Tokens are issued in two layers per SYSTEM_DESIGN_PHASE_2 §18.2:

* **Access JWT** — HS256-signed, ``AUTH_SECRET``, 15-minute TTL, no
  sliding extension.  Carries ``sub`` (user_id) and ``typ`` (``access`` |
  ``verify`` | ``reset`` | ``2fa_challenge``).
* **Refresh token** — opaque 32-byte random string returned to the
  caller; only its SHA-256 digest is stored in ``refresh_tokens``.
  Rotation happens on every use; presenting a token whose row is already
  ``revoked_at != NULL`` triggers full-chain revocation (reuse detection).

The reuse-detection contract is the security keystone:

1. Token A is issued.
2. The caller redeems A and receives token B.  A's row is marked
   ``revoked_at = now()``.
3. Later, *someone* presents A again — either the legitimate client
   replayed (e.g. retried after a network blip) or an attacker stole A
   from a logfile.  We cannot distinguish, so we treat both cases as
   compromise.  We revoke **every** non-revoked refresh-token row for
   that user and force re-authentication.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import RefreshToken
from app.services.auth.exceptions import (
    RefreshTokenReuseError,
    TokenExpiredError,
    TokenInvalidError,
)

JWT_ALG = "HS256"
ISSUER = "smart-resume"

TokenType = Literal["access", "verify", "reset", "2fa_challenge"]


# ---------------------------------------------------------------------------
# Access / single-purpose JWTs
# ---------------------------------------------------------------------------


def _require_secret() -> str:
    if not settings.AUTH_SECRET:
        raise RuntimeError(
            "AUTH_SECRET is not set. Configure it in backend/.env or your "
            "secret manager before issuing tokens."
        )
    return settings.AUTH_SECRET


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: str | uuid.UUID,
    *,
    ttl: int = 900,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Sign a 15-minute access JWT for ``user_id``.

    ``ttl`` overrides the default 900 s window — used by 2FA / verify /
    reset tokens via :func:`create_purpose_token`.
    """
    return _sign(user_id, typ="access", ttl=ttl, extra_claims=extra_claims)


def create_purpose_token(
    user_id: str | uuid.UUID,
    *,
    typ: TokenType,
    ttl: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Sign a typed, single-purpose JWT (verify / reset / 2fa_challenge)."""
    if typ == "access":
        raise ValueError("use create_access_token() for access tokens")
    return _sign(user_id, typ=typ, ttl=ttl, extra_claims=extra_claims)


def _sign(
    user_id: str | uuid.UUID,
    *,
    typ: TokenType,
    ttl: int,
    extra_claims: dict[str, Any] | None,
) -> str:
    now = _utcnow()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": typ,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "iss": ISSUER,
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        # Reserved claims always win.
        for k, v in extra_claims.items():
            payload.setdefault(k, v)
    return jwt.encode(payload, _require_secret(), algorithm=JWT_ALG)


def decode_access_token(token: str, *, expected_type: TokenType = "access") -> dict[str, Any]:
    """Verify a JWT signature + expiry and return its claims.

    Raises :class:`TokenExpiredError` on natural expiry and
    :class:`TokenInvalidError` on every other failure (bad signature,
    wrong issuer, wrong ``typ`` field).
    """
    try:
        claims = jwt.decode(
            token,
            _require_secret(),
            algorithms=[JWT_ALG],
            issuer=ISSUER,
            options={"require_sub": True, "require_exp": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("access token expired") from exc
    except JWTError as exc:
        raise TokenInvalidError(str(exc)) from exc

    if claims.get("typ") != expected_type:
        raise TokenInvalidError(
            f"token typ mismatch: expected {expected_type!r}, got {claims.get('typ')!r}"
        )
    return claims


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_device_fingerprint(user_agent: str, ip: str) -> str:
    """Deterministic SHA-256 of UA + IP (per §18.2).

    Lower-cases UA and ignores trailing whitespace so equivalent clients
    don't fragment into separate "devices".
    """
    raw = f"{(user_agent or '').strip().lower()}|{(ip or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """A refresh token + its DB row.

    ``token`` is the opaque string returned to the caller (and to the
    browser as a Secure HttpOnly cookie).  ``row`` is the persisted
    ``RefreshToken`` with the SHA-256 ``token_hash`` already stored.
    """

    token: str
    row: RefreshToken

    @property
    def token_id(self) -> uuid.UUID:
        return self.row.id

    @property
    def expires_at(self) -> datetime:
        return self.row.expires_at


async def create_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    device_fingerprint: str,
    parent_id: uuid.UUID | None = None,
    ttl_seconds: int | None = None,
) -> IssuedRefreshToken:
    """Issue and persist a fresh refresh token for ``user_id``.

    The plaintext token is generated server-side and is the only place it
    appears in plaintext during its lifetime — callers must hand it
    straight to the response (cookie / body) without logging.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.REFRESH_TOKEN_TTL_SECONDS
    token = secrets.token_urlsafe(48)
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=_hash_refresh(token),
        device_fingerprint=device_fingerprint,
        issued_at=_utcnow(),
        expires_at=_utcnow() + timedelta(seconds=ttl),
        parent_id=parent_id,
    )
    session.add(row)
    await session.flush()
    return IssuedRefreshToken(token=token, row=row)


async def revoke_token(session: AsyncSession, *, row: RefreshToken) -> None:
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        await session.flush()


async def revoke_all_user_tokens(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> int:
    """Revoke every active refresh token for ``user_id``. Returns the count revoked."""
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount or 0


async def find_refresh_token(
    session: AsyncSession,
    *,
    token: str,
    for_update: bool = False,
) -> RefreshToken | None:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(token))
    if for_update:
        # Prevent concurrent rotate requests from minting two child tokens
        # from the same parent token row.
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    token: str,
    device_fingerprint: str,
    ttl_seconds: int | None = None,
) -> IssuedRefreshToken:
    """Atomically exchange a refresh token for a fresh one.

    Security rules (§18.2 + §8.2):

    - Token must exist and not be expired.
    - If the matching row is already ``revoked_at != NULL`` we treat the
      presentation as **reuse**: revoke every still-active token for the
      same user and raise :class:`RefreshTokenReuseError`.
    - On success the old row is marked revoked and a brand-new token is
      issued with ``parent_id`` pointing at the old row.
    - Device fingerprint mismatch is *not* a hard error here (mobile
      networks rotate IPs constantly), but it is recorded onto the new
      token so auditors can spot anomalous patterns later.
    """
    row = await find_refresh_token(session, token=token, for_update=True)
    if row is None:
        raise TokenInvalidError("refresh token not recognised")

    if row.revoked_at is not None:
        # Reuse — revoke entire chain.
        await revoke_all_user_tokens(session, user_id=row.user_id)
        raise RefreshTokenReuseError(user_id=str(row.user_id))

    if row.expires_at <= _utcnow():
        raise TokenExpiredError("refresh token expired")

    # Mark old row revoked, then mint a new one chained to it.
    row.revoked_at = _utcnow()
    await session.flush()

    return await create_refresh_token(
        session,
        user_id=row.user_id,
        device_fingerprint=device_fingerprint,
        parent_id=row.id,
        ttl_seconds=ttl_seconds,
    )


# Test/debug helper: hash a token without DB roundtrip.
def hash_refresh_token(token: str) -> str:
    return _hash_refresh(token)


__all__ = [
    "ISSUER",
    "IssuedRefreshToken",
    "JWT_ALG",
    "TokenType",
    "create_access_token",
    "create_purpose_token",
    "create_refresh_token",
    "decode_access_token",
    "find_refresh_token",
    "hash_refresh_token",
    "make_device_fingerprint",
    "revoke_all_user_tokens",
    "revoke_token",
    "rotate_refresh_token",
]
