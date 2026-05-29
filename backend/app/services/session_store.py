from __future__ import annotations

import json
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
_lock_store: dict[str, bool] = {}
_redis_client: aioredis.Redis | None = None


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
    """Clear cached output so the next SSE run executes a fresh LLM call."""
    session = await get_session(session_id)
    if session is None:
        return
    setattr(session, f"phase{phase}_output", None)
    setattr(session, f"phase{phase}_status", "pending")
    await update_session(session)


# ---------------------------------------------------------------------------
# Phase lock — prevents concurrent agent runs per session
# ---------------------------------------------------------------------------

async def acquire_phase_lock(session_id: str, phase: int) -> bool:
    """Returns True if lock acquired. False if already running."""
    key = f"lock:{session_id}:phase{phase}"
    if _redis_client:
        result = await _redis_client.set(key, "1", nx=True, ex=300)
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
        _memory_store[session_id] = data


async def _load(session_id: str) -> str | None:
    if _redis_client:
        return await _redis_client.get(session_id)
    return _memory_store.get(session_id)


async def health_check() -> dict:
    if _redis_client:
        try:
            await _redis_client.ping()
            return {"redis": "ok"}
        except Exception as e:
            return {"redis": f"error: {e}"}
    return {"redis": "in-memory (dev mode)"}
