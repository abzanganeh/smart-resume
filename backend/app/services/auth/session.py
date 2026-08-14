"""Redis-backed refresh-token session metadata.

Each issued refresh token id is bound in Redis under
``refresh:{token_id}`` -> JSON ``{user_id, device_fingerprint, issued_at}``
with TTL matching the token's lifetime.  This gives the auth layer a fast,
cluster-wide revocation check that does not require a DB round-trip on
every API request.

We deliberately reuse the project's existing Redis client (initialised in
``app.services.session_store.init_redis``) so the connection pool is
shared and the in-memory fallback (used for ``USE_IN_MEMORY_STORE=true``
local dev) Just Works.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import settings
from app.services import session_store

# Key namespaces -----------------------------------------------------------

_TOKEN_KEY_FMT = "refresh:{token_id}"
_USER_INDEX_KEY_FMT = "refresh_user:{user_id}"
_ACTIVE_SESSION_KEY_FMT = "active_session:{user_id}"

# In-memory fallback for local dev / unit tests --------------------------------
_memory_tokens: dict[str, dict[str, Any]] = {}
_memory_user_index: dict[str, set[str]] = {}
_memory_active_sessions: dict[str, dict[str, Any]] = {}


def _redis() -> aioredis.Redis | None:
    """Return the shared Redis client if Redis mode is active."""
    return session_store._redis_client  # type: ignore[attr-defined]


def _token_key(token_id: uuid.UUID | str) -> str:
    return _TOKEN_KEY_FMT.format(token_id=str(token_id))


def _user_key(user_id: uuid.UUID | str) -> str:
    return _USER_INDEX_KEY_FMT.format(user_id=str(user_id))


def _active_session_key(user_id: uuid.UUID | str) -> str:
    return _ACTIVE_SESSION_KEY_FMT.format(user_id=str(user_id))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def bind_refresh_token_to_redis(
    token_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    device_fp: str,
    ttl: int | None = None,
    *,
    auth_session_id: uuid.UUID | str | None = None,
) -> None:
    """Persist a refresh token id with its metadata + TTL."""
    ttl_seconds = ttl if ttl is not None else settings.REFRESH_TOKEN_TTL_SECONDS
    payload_data: dict[str, Any] = {
        "user_id": str(user_id),
        "device_fingerprint": device_fp,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    if auth_session_id is not None:
        payload_data["auth_session_id"] = str(auth_session_id)
    payload = json.dumps(payload_data)
    r = _redis()
    if r is not None:
        async with r.pipeline(transaction=False) as pipe:
            pipe.setex(_token_key(token_id), ttl_seconds, payload)
            pipe.sadd(_user_key(user_id), str(token_id))
            # Re-stamp the index TTL so it always >= the longest member.
            pipe.expire(_user_key(user_id), ttl_seconds)
            await pipe.execute()
        return

    _memory_tokens[_token_key(token_id)] = {
        "payload": payload,
        "expires_at": datetime.now(timezone.utc).timestamp() + ttl_seconds,
    }
    _memory_user_index.setdefault(_user_key(user_id), set()).add(str(token_id))


async def get_refresh_token_metadata(
    token_id: uuid.UUID | str,
) -> dict[str, Any] | None:
    """Return the metadata blob for a token id or ``None`` if missing/revoked."""
    r = _redis()
    if r is not None:
        raw = await r.get(_token_key(token_id))
        return json.loads(raw) if raw else None

    entry = _memory_tokens.get(_token_key(token_id))
    if entry is None:
        return None
    if entry["expires_at"] <= datetime.now(timezone.utc).timestamp():
        _memory_tokens.pop(_token_key(token_id), None)
        return None
    return json.loads(entry["payload"])


async def revoke_redis_token(token_id: uuid.UUID | str) -> None:
    """Drop a single token id from Redis (idempotent)."""
    r = _redis()
    if r is not None:
        meta = await r.get(_token_key(token_id))
        await r.delete(_token_key(token_id))
        if meta:
            try:
                user_id = json.loads(meta).get("user_id")
            except (TypeError, ValueError):  # pragma: no cover - defensive
                user_id = None
            if user_id:
                await r.srem(_user_key(user_id), str(token_id))
        return

    entry = _memory_tokens.pop(_token_key(token_id), None)
    if entry is not None:
        try:
            user_id = json.loads(entry["payload"]).get("user_id")
        except (TypeError, ValueError):
            user_id = None
        if user_id:
            _memory_user_index.get(_user_key(user_id), set()).discard(str(token_id))


async def revoke_all_user_tokens(user_id: uuid.UUID | str) -> int:
    """Revoke every refresh token bound to ``user_id``.  Returns the count."""
    r = _redis()
    if r is not None:
        members = await r.smembers(_user_key(user_id))
        if not members:
            return 0
        keys = [_token_key(m) for m in members]
        async with r.pipeline(transaction=False) as pipe:
            pipe.delete(*keys)
            pipe.delete(_user_key(user_id))
            await pipe.execute()
        return len(members)

    members = list(_memory_user_index.pop(_user_key(user_id), set()))
    for m in members:
        _memory_tokens.pop(_token_key(m), None)
    return len(members)


async def list_user_token_ids(user_id: uuid.UUID | str) -> list[str]:
    """Return the live token-id set for ``user_id`` (for /sessions UI)."""
    r = _redis()
    if r is not None:
        members = await r.smembers(_user_key(user_id))
        return sorted(members)
    return sorted(_memory_user_index.get(_user_key(user_id), set()))


async def set_active_auth_session(
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
    *,
    ttl: int | None = None,
) -> None:
    """Record the sole active auth session id for ``user_id``."""
    ttl_seconds = ttl if ttl is not None else settings.REFRESH_TOKEN_TTL_SECONDS
    key = _active_session_key(user_id)
    value = str(session_id)
    r = _redis()
    if r is not None:
        await r.setex(key, ttl_seconds, value)
        return

    _memory_active_sessions[key] = {
        "session_id": value,
        "expires_at": datetime.now(timezone.utc).timestamp() + ttl_seconds,
    }


async def get_active_auth_session_id(user_id: uuid.UUID | str) -> str | None:
    """Return the current active auth session id or ``None``."""
    key = _active_session_key(user_id)
    r = _redis()
    if r is not None:
        raw = await r.get(key)
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    entry = _memory_active_sessions.get(key)
    if entry is None:
        return None
    if entry["expires_at"] <= datetime.now(timezone.utc).timestamp():
        _memory_active_sessions.pop(key, None)
        return None
    return entry["session_id"]


async def clear_active_auth_session(user_id: uuid.UUID | str) -> None:
    """Drop the active auth session marker for ``user_id`` (logout)."""
    key = _active_session_key(user_id)
    r = _redis()
    if r is not None:
        await r.delete(key)
        return
    _memory_active_sessions.pop(key, None)


def _reset_for_tests() -> None:
    """Clear the in-memory store between unit tests."""
    _memory_tokens.clear()
    _memory_user_index.clear()
    _memory_active_sessions.clear()


__all__ = [
    "bind_refresh_token_to_redis",
    "clear_active_auth_session",
    "get_active_auth_session_id",
    "get_refresh_token_metadata",
    "list_user_token_ids",
    "revoke_all_user_tokens",
    "revoke_redis_token",
    "set_active_auth_session",
]
