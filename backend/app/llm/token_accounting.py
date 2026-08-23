from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

import structlog
from pydantic import BaseModel, Field

from app.config import settings
from app.llm.base import LLMResponse
from app.llm.pricing import estimate_cost
from app.services import session_store

log = structlog.get_logger()


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


@contextmanager
def llm_accounting_context(session_id: str, step: str) -> Iterator[None]:
    """Bind resume session + pipeline step for downstream LLM token recording."""
    session_token: Token[str | None] = _llm_session_id.set(session_id)
    step_token: Token[str | None] = _llm_step.set(step)
    try:
        yield
    finally:
        _llm_session_id.reset(session_token)
        _llm_step.reset(step_token)


async def _load_runs(session_id: str) -> list[LLMRunRecord]:
    raw = await session_store.redis_get(_usage_key(session_id))
    if not raw:
        return []
    payload = json.loads(raw)
    return [LLMRunRecord.model_validate(item) for item in payload]


async def _save_runs(session_id: str, runs: list[LLMRunRecord]) -> None:
    await session_store.redis_set(
        _usage_key(session_id),
        json.dumps([run.model_dump() for run in runs]),
        ex=settings.SESSION_TTL_SECONDS,
    )


async def record_llm_response(
    response: LLMResponse,
    *,
    step: str | None = None,
    session_id: str | None = None,
) -> LLMRunRecord:
    """Persist provider-reported token counts for one completion (content never logged)."""
    sid = session_id or _llm_session_id.get()
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
        step=step_name,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_cost_usd=cost,
    )
    if sid:
        runs = await _load_runs(sid)
        runs.append(record)
        await _save_runs(sid, runs)
        used = session_token_total(
            SessionTokenTotals(
                input_tokens=sum(r.input_tokens for r in runs),
                output_tokens=sum(r.output_tokens for r in runs),
                estimated_cost_usd=round(sum(r.estimated_cost_usd for r in runs), 6),
                run_count=len(runs),
                runs=runs,
            )
        )
        ceiling = settings.SESSION_LLM_TOKEN_CEILING
        if used >= ceiling:
            raise SessionTokenBudgetExceeded(sid, used=used, ceiling=ceiling)
    return record


async def get_session_token_totals(session_id: str) -> SessionTokenTotals:
    """Return per-run records and summed token/cost totals for a resume session."""
    runs = await _load_runs(session_id)
    return SessionTokenTotals(
        input_tokens=sum(run.input_tokens for run in runs),
        output_tokens=sum(run.output_tokens for run in runs),
        estimated_cost_usd=round(sum(run.estimated_cost_usd for run in runs), 6),
        run_count=len(runs),
        runs=runs,
    )


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
    """Reset stored usage — for tests only."""
    await session_store.redis_delete(_usage_key(session_id))
