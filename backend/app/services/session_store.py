from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import settings
from app.models.session import PhaseStatus, Session

# ---------------------------------------------------------------------------
# In-memory fallback (for local dev without Redis)
# ---------------------------------------------------------------------------
_memory_store: dict[str, str] = {}
_memory_expiry: dict[str, float] = {}  # key -> unix timestamp when key expires
_lock_store: dict[str, bool] = {}
_redis_client: aioredis.Redis | None = None


def _mem_get(key: str) -> str | None:
    """Read a key from the in-memory store, respecting TTL."""
    exp = _memory_expiry.get(key)
    if exp is not None and time.monotonic() > exp:
        _memory_store.pop(key, None)
        _memory_expiry.pop(key, None)
        return None
    return _memory_store.get(key)


def _mem_set(key: str, value: str, *, ex: int | None = None) -> None:
    _memory_store[key] = value
    if ex is not None:
        _memory_expiry[key] = time.monotonic() + ex
    else:
        _memory_expiry.pop(key, None)


def _mem_delete(key: str) -> str | None:
    _memory_expiry.pop(key, None)
    return _memory_store.pop(key, None)


async def init_redis() -> None:
    global _redis_client
    if not settings.USE_IN_MEMORY_STORE:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def close_redis() -> None:
    if _redis_client:
        await _redis_client.aclose()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

async def create_session(provider: str | None = None, model: str | None = None) -> Session:
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    session = Session(
        session_id=sid,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.SESSION_TTL_SECONDS),
        provider=provider or settings.LLM_PROVIDER,
        model=model or settings.LLM_MODEL,
    )
    await _save(sid, session)
    return session


async def get_session(session_id: str) -> Session | None:
    data = await _load(session_id)
    if data is None:
        return None
    return Session.model_validate_json(data)


async def update_session(session: Session) -> None:
    await _save(session.session_id, session)


async def update_phase_status(session_id: str, phase: int, status: str) -> None:
    session = await get_session(session_id)
    if session is None:
        return
    setattr(session, f"phase{phase}_status", status)
    await update_session(session)


async def save_phase_output(session_id: str, phase: int, output: Any) -> None:
    session = await get_session(session_id)
    if session is None:
        return
    setattr(session, f"phase{phase}_output", output)
    setattr(session, f"phase{phase}_status", PhaseStatus.done)
    await update_session(session)


async def reset_phase(session_id: str, phase: int) -> None:
    """Clear cached output and any held lock so the next run executes fresh.

    Also drops the Redis phase lock — without this, a previous run that died
    mid-flight (e.g. backend restart, network drop) can leave both the
    ``phase{n}_status="running"`` flag and the lock in place, blocking
    every subsequent ``force=true`` rerun with a 409.
    """
    session = await get_session(session_id)
    if session is None:
        return
    setattr(session, f"phase{phase}_output", None)
    setattr(session, f"phase{phase}_status", "pending")
    await update_session(session)
    await release_phase_lock(session_id, phase)


async def is_phase_lock_held(session_id: str, phase: int) -> bool:
    """Probe whether the Redis phase lock is currently held."""
    key = f"lock:{session_id}:phase{phase}"
    if _redis_client:
        return bool(await _redis_client.exists(key))
    return bool(_lock_store.get(key))


# ---------------------------------------------------------------------------
# Phase lock — prevents concurrent agent runs per session
# ---------------------------------------------------------------------------

async def acquire_phase_lock(session_id: str, phase: int) -> bool:
    """Returns True if lock acquired. False if already running."""
    key = f"lock:{session_id}:phase{phase}"
    if _redis_client:
        result = await _redis_client.set(key, "1", nx=True, ex=settings.PHASE_LOCK_TTL_SECONDS)
        return result is True
    else:
        if _lock_store.get(key):
            return False
        _lock_store[key] = True
        return True


async def release_phase_lock(session_id: str, phase: int) -> None:
    key = f"lock:{session_id}:phase{phase}"
    if _redis_client:
        await _redis_client.delete(key)
    else:
        _lock_store.pop(key, None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _save(session_id: str, session: Session) -> None:
    data = session.model_dump_json()
    if _redis_client:
        await _redis_client.setex(session_id, settings.SESSION_TTL_SECONDS, data)
    else:
        _mem_set(session_id, data, ex=settings.SESSION_TTL_SECONDS)


async def _load(session_id: str) -> str | None:
    if _redis_client:
        return await _redis_client.get(session_id)
    return _mem_get(session_id)


async def health_check() -> dict:
    if _redis_client:
        try:
            await _redis_client.ping()
            return {"redis": "ok"}
        except Exception as e:
            return {"redis": f"error: {e}"}
    return {"redis": "in-memory (dev mode)"}


def redis_available() -> bool:
    """Return True when a live Redis client is connected."""
    return _redis_client is not None


async def redis_get(key: str) -> str | None:
    if _redis_client:
        return await _redis_client.get(key)
    return _mem_get(key)


async def redis_getdel(key: str) -> str | None:
    """Atomically fetch and delete a key (single-use token redeem)."""
    if _redis_client:
        return await _redis_client.getdel(key)
    return _mem_delete(key)


async def redis_set(key: str, value: str, *, ex: int | None = None) -> None:
    if _redis_client:
        if ex is not None:
            await _redis_client.setex(key, ex, value)
        else:
            await _redis_client.set(key, value)
    else:
        _mem_set(key, value, ex=ex)


async def redis_set_nx(key: str, value: str, *, ex: int | None = None) -> bool:
    """Set key only when absent. Returns True when set."""
    if _redis_client:
        result = await _redis_client.set(key, value, nx=True, ex=ex)
        return result is True
    if _mem_get(key) is not None:
        return False
    _mem_set(key, value, ex=ex)
    return True


async def redis_delete(*keys: str) -> None:
    if _redis_client:
        if keys:
            await _redis_client.delete(*keys)
    else:
        for key in keys:
            _mem_delete(key)


async def redis_expire(key: str, seconds: int) -> None:
    if _redis_client:
        await _redis_client.expire(key, seconds)
    else:
        if key in _memory_store:
            _memory_expiry[key] = time.monotonic() + seconds


async def redis_incr(key: str) -> int:
    if _redis_client:
        return int(await _redis_client.incr(key))
    current = int(_mem_get(key) or "0")
    current += 1
    # Preserve existing TTL when incrementing.
    existing_exp = _memory_expiry.get(key)
    _memory_store[key] = str(current)
    if existing_exp is not None:
        _memory_expiry[key] = existing_exp
    return current


async def redis_incrbyfloat(key: str, amount: float) -> float:
    """Atomically increment a float counter — INCRBYFLOAT on Redis.

    Fallback path preserves any existing TTL and mirrors Redis semantics.
    """
    if _redis_client:
        return float(await _redis_client.incrbyfloat(key, amount))
    current_raw = _mem_get(key)
    try:
        current = float(current_raw) if current_raw is not None else 0.0
    except ValueError:
        current = 0.0
    new_value = current + amount
    existing_exp = _memory_expiry.get(key)
    _memory_store[key] = f"{new_value:.6f}"
    if existing_exp is not None:
        _memory_expiry[key] = existing_exp
    return new_value


async def reset_redis_keys_for_tests() -> None:
    """Clear in-memory Redis fallback between tests."""
    if not _redis_client:
        keys = [
            k
            for k in list(_memory_store)
            if k.startswith(("hirebase:", "flint:handoff:", "flint:handoff:rate:"))
        ]
        for key in keys:
            _memory_store.pop(key, None)
            _memory_expiry.pop(key, None)
