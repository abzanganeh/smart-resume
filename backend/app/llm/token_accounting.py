from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Iterator

import structlog
from pydantic import BaseModel, Field

from app.config import settings
from app.llm.base import LLMResponse
from app.llm.pricing import estimate_cost
from app.services import session_store

log = structlog.get_logger()

_PLATFORM_USAGE_TTL_SECONDS = 90 * 24 * 3600
_USER_USAGE_TTL_SECONDS = 90 * 24 * 3600


class SessionTokenBudgetExceeded(Exception):
    """Raised when a resume session exceeds the configured LLM token ceiling."""

    def __init__(self, session_id: str, *, used: int, ceiling: int) -> None:
        self.session_id = session_id
        self.used = used
        self.ceiling = ceiling
        super().__init__(
            f"Session {session_id} exceeded LLM token budget ({used} >= {ceiling})"
        )

_llm_session_id: ContextVar[str | None] = ContextVar("llm_session_id", default=None)
_llm_step: ContextVar[str | None] = ContextVar("llm_step", default=None)
_llm_user_id: ContextVar[str | None] = ContextVar("llm_user_id", default=None)


class LLMRunRecord(BaseModel):
    step: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class SessionTokenTotals(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    run_count: int = 0
    runs: list[LLMRunRecord] = Field(default_factory=list)


def _usage_key(session_id: str) -> str:
    return f"llm_usage:{session_id}"


def _user_usage_key(user_id: str) -> str:
    return f"llm_usage:user:{user_id}"


def _platform_usage_key(day: str | None = None) -> str:
    utc_day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"llm_usage:platform:{utc_day}"


@contextmanager
def llm_accounting_context(
    session_id: str | None = None,
    step: str = "unknown",
    *,
    user_id: str | None = None,
) -> Iterator[None]:
    """Bind session, user, and pipeline step for downstream LLM token recording."""
    tokens: list[Token[str | None]] = []
    if session_id is not None:
        tokens.append(("session", _llm_session_id.set(session_id)))
    if step:
        tokens.append(("step", _llm_step.set(step)))
    if user_id is not None:
        tokens.append(("user", _llm_user_id.set(user_id)))
    try:
        yield
    finally:
        for kind, token in reversed(tokens):
            if kind == "session":
                _llm_session_id.reset(token)
            elif kind == "step":
                _llm_step.reset(token)
            else:
                _llm_user_id.reset(token)


async def _load_records(key: str) -> list[LLMRunRecord]:
    raw = await session_store.redis_get(key)
    if not raw:
        return []
    payload = json.loads(raw)
    return [LLMRunRecord.model_validate(item) for item in payload]


async def _save_records(key: str, runs: list[LLMRunRecord], *, ttl_seconds: int) -> None:
    await session_store.redis_set(
        key,
        json.dumps([run.model_dump() for run in runs]),
        ex=ttl_seconds,
    )


async def _append_record(key: str, record: LLMRunRecord, *, ttl_seconds: int) -> list[LLMRunRecord]:
    runs = await _load_records(key)
    runs.append(record)
    await _save_records(key, runs, ttl_seconds=ttl_seconds)
    return runs


def _totals_from_runs(runs: list[LLMRunRecord]) -> SessionTokenTotals:
    return SessionTokenTotals(
        input_tokens=sum(run.input_tokens for run in runs),
        output_tokens=sum(run.output_tokens for run in runs),
        estimated_cost_usd=round(sum(run.estimated_cost_usd for run in runs), 6),
        run_count=len(runs),
        runs=runs,
    )


async def record_llm_response(
    response: LLMResponse,
    *,
    step: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> LLMRunRecord:
    """Persist provider-reported token counts for one completion (content never logged)."""
    sid = session_id or _llm_session_id.get()
    uid = user_id or _llm_user_id.get()
    step_name = step or _llm_step.get() or "unknown"
    cost = estimate_cost(
        response.input_tokens,
        response.output_tokens,
        response.provider,
        response.model,
    )
    record = LLMRunRecord(
        step=step_name,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_cost_usd=cost,
    )
    log.info(
        "llm_run_tokens",
        session_id=sid,
        user_id=uid,
        step=step_name,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_cost_usd=cost,
    )

    await _append_record(
        _platform_usage_key(),
        record,
        ttl_seconds=_PLATFORM_USAGE_TTL_SECONDS,
    )
    if uid:
        await _append_record(
            _user_usage_key(uid),
            record,
            ttl_seconds=_USER_USAGE_TTL_SECONDS,
        )
    if sid:
        runs = await _append_record(
            _usage_key(sid),
            record,
            ttl_seconds=settings.SESSION_TTL_SECONDS,
        )
        used = session_token_total(_totals_from_runs(runs))
        ceiling = settings.SESSION_LLM_TOKEN_CEILING
        if used >= ceiling:
            raise SessionTokenBudgetExceeded(sid, used=used, ceiling=ceiling)
    return record


async def get_session_token_totals(session_id: str) -> SessionTokenTotals:
    """Return per-run records and summed token/cost totals for a resume session."""
    runs = await _load_records(_usage_key(session_id))
    return _totals_from_runs(runs)


async def get_user_token_totals(user_id: str) -> SessionTokenTotals:
    """Return per-run records and summed token/cost totals for a user."""
    runs = await _load_records(_user_usage_key(user_id))
    return _totals_from_runs(runs)


async def get_platform_token_totals(day: str | None = None) -> SessionTokenTotals:
    """Return summed token/cost totals for platform-managed LLM usage on a UTC day."""
    runs = await _load_records(_platform_usage_key(day))
    return _totals_from_runs(runs)


def session_token_total(totals: SessionTokenTotals) -> int:
    return totals.input_tokens + totals.output_tokens


async def assert_session_within_token_ceiling(session_id: str) -> SessionTokenTotals:
    """Raise when the session has hit the configured LLM token budget."""
    totals = await get_session_token_totals(session_id)
    used = session_token_total(totals)
    ceiling = settings.SESSION_LLM_TOKEN_CEILING
    if used >= ceiling:
        raise SessionTokenBudgetExceeded(session_id, used=used, ceiling=ceiling)
    return totals


async def clear_session_token_totals(session_id: str) -> None:
    """Reset stored session usage — for tests only."""
    await session_store.redis_delete(_usage_key(session_id))


async def clear_user_token_totals(user_id: str) -> None:
    """Reset stored user usage — for tests only."""
    await session_store.redis_delete(_user_usage_key(user_id))


async def clear_platform_token_totals(day: str | None = None) -> None:
    """Reset stored platform usage — for tests only."""
    await session_store.redis_delete(_platform_usage_key(day))
