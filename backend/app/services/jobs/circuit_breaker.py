"""Hirebase circuit breaker backed by Redis (SYSTEM_DESIGN_PHASE_2 §18.10)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from app.services.session_store import (
    redis_delete,
    redis_get,
    redis_incr,
    redis_set,
)

log = structlog.get_logger("jobs.circuit_breaker")

FAILURES_KEY = "hirebase:failures"
OPEN_UNTIL_KEY = "hirebase:open_until"
PROBE_LOCK_KEY = "hirebase:probe_lock"

FAILURE_THRESHOLD = 5
COOLDOWN_SECONDS = 300  # 5 minutes
FAILURE_WINDOW_SECONDS = 60


class HirebaseUnavailableError(Exception):
    """Raised when the circuit is open and a live Hirebase call is not allowed."""


@dataclass(frozen=True, slots=True)
class CircuitState:
    is_open: bool
    open_until: datetime | None
    consecutive_failures: int
    allow_probe: bool


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


async def get_circuit_state() -> CircuitState:
    failures_raw = await redis_get(FAILURES_KEY)
    failures = int(failures_raw or "0")
    open_until_raw = await redis_get(OPEN_UNTIL_KEY)
    open_until_ts = float(open_until_raw) if open_until_raw else None
    now = _now_ts()

    if open_until_ts is None:
        return CircuitState(
            is_open=False,
            open_until=None,
            consecutive_failures=failures,
            allow_probe=False,
        )

    if now >= open_until_ts:
        # Cool-down elapsed — allow a single probe request.
        return CircuitState(
            is_open=True,
            open_until=datetime.fromtimestamp(open_until_ts, tz=timezone.utc),
            consecutive_failures=failures,
            allow_probe=True,
        )

    return CircuitState(
        is_open=True,
        open_until=datetime.fromtimestamp(open_until_ts, tz=timezone.utc),
        consecutive_failures=failures,
        allow_probe=False,
    )


async def record_success() -> None:
    await redis_delete(FAILURES_KEY, OPEN_UNTIL_KEY, PROBE_LOCK_KEY)


async def _open_circuit(*, reason: str) -> None:
    until = _now_ts() + COOLDOWN_SECONDS
    await redis_set(OPEN_UNTIL_KEY, str(until), ex=COOLDOWN_SECONDS + 60)
    log.warning("hirebase.circuit_opened", reason=reason, cooldown_seconds=COOLDOWN_SECONDS)


async def record_failure(*, status_code: int | None = None) -> None:
    """Record a Hirebase failure; open circuit when thresholds are met."""
    if status_code is not None and (status_code == 429 or status_code >= 500):
        await redis_incr(FAILURES_KEY)
        await _open_circuit(reason=f"http_{status_code}")
        return

    count = await redis_incr(FAILURES_KEY)
    if count >= FAILURE_THRESHOLD:
        await _open_circuit(reason="consecutive_failures")


async def record_probe_failure() -> None:
    """Probe failed — reset the 5-minute cool-down."""
    await _open_circuit(reason="probe_failed")


async def acquire_probe_slot() -> bool:
    """Return True if this request may act as the single probe after cool-down."""
    existing = await redis_get(PROBE_LOCK_KEY)
    if existing:
        return False
    await redis_set(PROBE_LOCK_KEY, "1", ex=COOLDOWN_SECONDS)
    return True


async def assert_call_allowed() -> CircuitState:
    """Raise :class:`HirebaseUnavailableError` when the circuit blocks live calls."""
    state = await get_circuit_state()
    if not state.is_open:
        return state
    if state.allow_probe and await acquire_probe_slot():
        return state
    raise HirebaseUnavailableError("hirebase_circuit_open")


__all__ = [
    "CircuitState",
    "HirebaseUnavailableError",
    "acquire_probe_slot",
    "assert_call_allowed",
    "get_circuit_state",
    "record_failure",
    "record_probe_failure",
    "record_success",
]
