"""Admin JWT issuance / verification + Redis session binding.

Three admin token types (IMPLEMENTATION_PLAN section 8.4.2):

1. ``admin_2fa_setup``  -- 15-minute TTL.  Issued on first login when
   the admin has not yet enrolled TOTP.  Only the
   ``/api/admin/auth/2fa/enroll`` and ``/api/admin/auth/2fa/verify``
   endpoints accept it.

2. ``admin_challenge``  -- 15-minute TTL.  Issued on credentials login
   when 2FA is already enrolled.  Only ``/api/admin/auth/2fa/verify``
   accepts it.

3. ``admin_session``    -- 60-minute absolute TTL, 15-minute idle TTL,
   bound to an IP address and a User-Agent fingerprint.  Issued only
   after a successful TOTP verification.  Storage is split:

   - The signed JWT carries ``sub`` (admin id), ``sid`` (session id),
     ``ip``, ``ua``, ``iat``, ``exp``.  Replaying the JWT with a
     different IP / UA is rejected by ``decode_admin_session_token``.
   - A Redis row keyed by ``admin_session:{sid}`` stores the same
     binding plus ``last_active_at`` and is hard-revoked on logout /
     2FA reset / role change / super-admin force-logout.  When Redis is
     unavailable we fall back to the JWT alone (local dev / unit tests
     via the in-memory store).

We deliberately do NOT reuse ``app.services.auth.tokens`` for these
helpers because the admin claims set is distinct (``ip``/``ua``
binding, separate ``typ`` namespace, different TTLs) and folding them
into the user-side helper would muddy the contract.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt

from app.config import settings
from app.services import session_store

ADMIN_JWT_ALG = "HS256"
ADMIN_JWT_ISSUER = "smart-resume-admin"

AdminTokenType = Literal["admin_2fa_setup", "admin_challenge", "admin_session"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AdminTokenError(Exception):
    """Base class for admin-token decode failures."""


class AdminTokenInvalid(AdminTokenError):
    """Signature mismatch, wrong issuer, wrong type."""


class AdminTokenExpired(AdminTokenError):
    """Natural expiry."""


class AdminSessionNotFound(AdminTokenError):
    """Token decoded fine but no live session record (revoked / Redis miss)."""


class AdminSessionBindingMismatch(AdminTokenError):
    """IP or UA fingerprint differs from the issuance value."""


class AdminSessionIdle(AdminTokenError):
    """Session passed absolute TTL but failed the idle-window check."""


# ---------------------------------------------------------------------------
# UA fingerprinting
# ---------------------------------------------------------------------------


def make_ua_fingerprint(user_agent: str, accept_language: str) -> str:
    """Stable SHA-256 hash of UA + Accept-Language (section 8.4.2).

    Lower-cases both inputs and ignores trailing whitespace so equivalent
    clients do not fragment.
    """
    raw = f"{(user_agent or '').strip().lower()}|{(accept_language or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _require_secret() -> str:
    if not settings.AUTH_SECRET:
        raise RuntimeError(
            "AUTH_SECRET is not set; admin tokens cannot be signed. "
            "Configure it in backend/.env or your secret manager."
        )
    return settings.AUTH_SECRET


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sign(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, _require_secret(), algorithm=ADMIN_JWT_ALG)


def _decode_raw(token: str, *, expected_type: AdminTokenType) -> dict[str, Any]:
    try:
        decoded = jwt.decode(
            token,
            _require_secret(),
            algorithms=[ADMIN_JWT_ALG],
            issuer=ADMIN_JWT_ISSUER,
            options={"require_sub": True, "require_exp": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AdminTokenExpired("admin token expired") from exc
    except JWTError as exc:
        raise AdminTokenInvalid(str(exc)) from exc
    if decoded.get("typ") != expected_type:
        raise AdminTokenInvalid(
            f"token typ mismatch: expected {expected_type!r}, got {decoded.get('typ')!r}"
        )
    return decoded


# ---------------------------------------------------------------------------
# admin_2fa_setup token
# ---------------------------------------------------------------------------


def create_admin_2fa_setup_token(
    admin_id: str | uuid.UUID,
    *,
    ttl: int | None = None,
) -> str:
    """Issue a short-lived JWT used to walk a new admin through TOTP enrollment.

    Only ``/api/admin/auth/2fa/enroll`` and ``/api/admin/auth/2fa/verify``
    accept it.  No IP / UA binding -- enrollment must work from a
    different IP than the original credentials post.
    """
    now = _utcnow()
    ttl_seconds = ttl if ttl is not None else settings.ADMIN_2FA_SETUP_TTL_SECONDS
    claims = {
        "sub": str(admin_id),
        "typ": "admin_2fa_setup",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "iss": ADMIN_JWT_ISSUER,
        "jti": secrets.token_urlsafe(16),
    }
    return _sign(claims)


def decode_admin_2fa_setup_token(token: str) -> dict[str, Any]:
    return _decode_raw(token, expected_type="admin_2fa_setup")


# ---------------------------------------------------------------------------
# admin_challenge token
# ---------------------------------------------------------------------------


def create_admin_challenge_token(
    admin_id: str | uuid.UUID,
    *,
    ttl: int | None = None,
) -> str:
    """Mint a short-lived challenge token expecting TOTP next."""
    now = _utcnow()
    ttl_seconds = ttl if ttl is not None else settings.ADMIN_CHALLENGE_TTL_SECONDS
    claims = {
        "sub": str(admin_id),
        "typ": "admin_challenge",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "iss": ADMIN_JWT_ISSUER,
        "jti": secrets.token_urlsafe(16),
    }
    return _sign(claims)


def decode_admin_challenge_token(token: str) -> dict[str, Any]:
    return _decode_raw(token, expected_type="admin_challenge")


# ---------------------------------------------------------------------------
# admin_session token + Redis binding
# ---------------------------------------------------------------------------


_ADMIN_SESSION_KEY_FMT = "admin_session:{sid}"
_ADMIN_SESSION_INDEX_FMT = "admin_session_index:{admin_id}"

# In-memory fallback used by tests / local dev (USE_IN_MEMORY_STORE=true).
_memory_sessions: dict[str, dict[str, Any]] = {}
_memory_session_index: dict[str, set[str]] = {}


def _session_key(sid: str) -> str:
    return _ADMIN_SESSION_KEY_FMT.format(sid=sid)


def _session_index_key(admin_id: str) -> str:
    return _ADMIN_SESSION_INDEX_FMT.format(admin_id=admin_id)


@dataclass(frozen=True, slots=True)
class IssuedAdminSession:
    """Return value of :func:`create_admin_session_token`."""

    token: str
    session_id: str
    admin_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime
    idle_expires_at: datetime
    ip: str
    ua_fingerprint: str


async def create_admin_session_token(
    admin_id: str | uuid.UUID,
    ip: str,
    ua_fingerprint: str,
    ttl: int | None = None,
    idle_ttl: int | None = None,
) -> IssuedAdminSession:
    """Mint a full admin session token and persist its Redis binding.

    Only callable after a successful TOTP verification.  Returns the
    signed JWT plus the metadata so the route handler can update
    ``last_login_at`` and audit the issuance.
    """
    now = _utcnow()
    ttl_seconds = ttl if ttl is not None else settings.ADMIN_SESSION_TTL_SECONDS
    idle_seconds = (
        idle_ttl if idle_ttl is not None else settings.ADMIN_SESSION_IDLE_TTL_SECONDS
    )
    sid = uuid.uuid4().hex
    claims = {
        "sub": str(admin_id),
        "typ": "admin_session",
        "sid": sid,
        "ip": ip,
        "ua": ua_fingerprint,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "iss": ADMIN_JWT_ISSUER,
        "jti": secrets.token_urlsafe(16),
    }
    token = _sign(claims)
    expires_at = now + timedelta(seconds=ttl_seconds)
    idle_expires_at = now + timedelta(seconds=idle_seconds)

    payload = json.dumps(
        {
            "admin_id": str(admin_id),
            "ip": ip,
            "ua": ua_fingerprint,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_active_at": now.isoformat(),
        }
    )

    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        async with r.pipeline(transaction=False) as pipe:
            pipe.setex(_session_key(sid), ttl_seconds, payload)
            pipe.sadd(_session_index_key(str(admin_id)), sid)
            pipe.expire(_session_index_key(str(admin_id)), ttl_seconds)
            await pipe.execute()
    else:
        _memory_sessions[_session_key(sid)] = {
            "payload": payload,
            "expires_at": expires_at.timestamp(),
            "last_active_at": now.timestamp(),
        }
        _memory_session_index.setdefault(_session_index_key(str(admin_id)), set()).add(sid)

    return IssuedAdminSession(
        token=token,
        session_id=sid,
        admin_id=uuid.UUID(str(admin_id)),
        issued_at=now,
        expires_at=expires_at,
        idle_expires_at=idle_expires_at,
        ip=ip,
        ua_fingerprint=ua_fingerprint,
    )


async def _read_session_record(sid: str) -> dict[str, Any] | None:
    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        raw = await r.get(_session_key(sid))
        return json.loads(raw) if raw else None
    entry = _memory_sessions.get(_session_key(sid))
    if entry is None:
        return None
    if entry["expires_at"] <= _utcnow().timestamp():
        _memory_sessions.pop(_session_key(sid), None)
        return None
    return json.loads(entry["payload"]) | {"last_active_at": entry["last_active_at"]}


async def _touch_session_activity(sid: str) -> None:
    """Update ``last_active_at`` so idle TTL is computed against the
    most recent observed request."""
    now = _utcnow()
    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        raw = await r.get(_session_key(sid))
        if not raw:
            return
        data = json.loads(raw)
        data["last_active_at"] = now.isoformat()
        # Preserve the absolute TTL; recompute remaining seconds.
        try:
            expires_at = datetime.fromisoformat(data["expires_at"])
            ttl_remaining = max(int((expires_at - now).total_seconds()), 1)
        except Exception:  # pragma: no cover - defensive
            ttl_remaining = settings.ADMIN_SESSION_TTL_SECONDS
        await r.setex(_session_key(sid), ttl_remaining, json.dumps(data))
        return
    entry = _memory_sessions.get(_session_key(sid))
    if entry is not None:
        entry["last_active_at"] = now.timestamp()


async def revoke_admin_session(sid: str) -> None:
    """Drop a single admin session id (idempotent)."""
    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        raw = await r.get(_session_key(sid))
        await r.delete(_session_key(sid))
        if raw:
            try:
                data = json.loads(raw)
                admin_id = data.get("admin_id", "")
            except (TypeError, ValueError):
                admin_id = ""
            if admin_id:
                await r.srem(_session_index_key(admin_id), sid)
        return
    entry = _memory_sessions.pop(_session_key(sid), None)
    if entry is not None:
        try:
            data = json.loads(entry["payload"])
            admin_id = data.get("admin_id", "")
        except (TypeError, ValueError):
            admin_id = ""
        if admin_id:
            _memory_session_index.get(_session_index_key(admin_id), set()).discard(sid)


async def revoke_all_admin_sessions(admin_id: str | uuid.UUID) -> int:
    """Revoke every active session for ``admin_id``.  Returns the count."""
    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        members = await r.smembers(_session_index_key(str(admin_id)))
        if not members:
            return 0
        keys = [_session_key(m) for m in members]
        async with r.pipeline(transaction=False) as pipe:
            pipe.delete(*keys)
            pipe.delete(_session_index_key(str(admin_id)))
            await pipe.execute()
        return len(members)
    members = list(_memory_session_index.pop(_session_index_key(str(admin_id)), set()))
    for m in members:
        _memory_sessions.pop(_session_key(m), None)
    return len(members)


@dataclass(frozen=True, slots=True)
class AdminSessionClaims:
    """Verified admin-session token claims."""

    admin_id: uuid.UUID
    session_id: str
    ip: str
    ua_fingerprint: str
    issued_at: datetime
    expires_at: datetime


async def decode_admin_session_token(
    token: str,
    *,
    request_ip: str,
    request_ua_fingerprint: str,
) -> AdminSessionClaims:
    """Verify a session token and check IP / UA / idle-TTL bindings.

    Raises:
        AdminTokenInvalid       : signature / type / claim shape problem.
        AdminTokenExpired       : absolute TTL elapsed.
        AdminSessionNotFound    : Redis row gone (revoked / TTL miss).
        AdminSessionBindingMismatch : IP or UA differs from issuance.
        AdminSessionIdle        : idle window elapsed.
    """
    raw = _decode_raw(token, expected_type="admin_session")
    sid = str(raw.get("sid") or "")
    bound_ip = str(raw.get("ip") or "")
    bound_ua = str(raw.get("ua") or "")
    if not sid or not bound_ip or not bound_ua:
        raise AdminTokenInvalid("admin session token missing binding claims")

    record = await _read_session_record(sid)
    if record is None:
        raise AdminSessionNotFound("admin session revoked or expired")

    if record.get("ip") != bound_ip or record.get("ua") != bound_ua:
        # Defensive: someone tampered with the JWT without invalidating
        # the Redis record.  Treat as binding mismatch.
        raise AdminSessionBindingMismatch("admin session binding tampered")

    if request_ip and request_ip != bound_ip:
        raise AdminSessionBindingMismatch(
            f"admin session ip mismatch: bound={bound_ip!r}, request={request_ip!r}"
        )
    if request_ua_fingerprint and request_ua_fingerprint != bound_ua:
        raise AdminSessionBindingMismatch(
            "admin session user-agent fingerprint mismatch"
        )

    now = _utcnow()
    last_active_str = record.get("last_active_at") or record.get("issued_at")
    try:
        last_active = datetime.fromisoformat(str(last_active_str))
    except (TypeError, ValueError):
        last_active = now
    if (now - last_active).total_seconds() > settings.ADMIN_SESSION_IDLE_TTL_SECONDS:
        await revoke_admin_session(sid)
        raise AdminSessionIdle("admin session idle window elapsed")

    # All checks passed - bump activity timestamp so idle-window slides
    # forward.  The absolute TTL stays anchored to issuance.
    await _touch_session_activity(sid)

    issued_at = datetime.fromtimestamp(int(raw["iat"]), tz=timezone.utc)
    expires_at = datetime.fromtimestamp(int(raw["exp"]), tz=timezone.utc)
    return AdminSessionClaims(
        admin_id=uuid.UUID(str(raw["sub"])),
        session_id=sid,
        ip=bound_ip,
        ua_fingerprint=bound_ua,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def _reset_for_tests() -> None:
    """Clear in-memory session store between unit tests."""
    _memory_sessions.clear()
    _memory_session_index.clear()


__all__ = [
    "ADMIN_JWT_ISSUER",
    "AdminSessionBindingMismatch",
    "AdminSessionClaims",
    "AdminSessionIdle",
    "AdminSessionNotFound",
    "AdminTokenError",
    "AdminTokenExpired",
    "AdminTokenInvalid",
    "AdminTokenType",
    "IssuedAdminSession",
    "create_admin_2fa_setup_token",
    "create_admin_challenge_token",
    "create_admin_session_token",
    "decode_admin_2fa_setup_token",
    "decode_admin_challenge_token",
    "decode_admin_session_token",
    "make_ua_fingerprint",
    "revoke_admin_session",
    "revoke_all_admin_sessions",
]
