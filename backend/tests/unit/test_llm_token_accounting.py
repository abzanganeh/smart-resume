"""Token accounting regression tests (M18 slice 2)."""

from __future__ import annotations

import pytest

from app.llm.base import LLMResponse
from app.llm.token_accounting import (
    clear_session_token_totals,
    get_session_token_totals,
    llm_accounting_context,
    record_llm_response,
)


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def _clear_usage_store() -> None:
    await clear_session_token_totals("sess-a")
    await clear_session_token_totals("sess-b")


@pytest.mark.asyncio
async def test_record_llm_response_persists_and_sums_per_session() -> None:
    response = LLMResponse(
        content="should never appear in logs",
        input_tokens=1000,
        output_tokens=500,
        model="gemini-2.5-flash-lite",
        provider="gemini",
    )
    with llm_accounting_context("sess-a", "phase1"):
        await record_llm_response(response)
    with llm_accounting_context("sess-a", "phase2"):
        await record_llm_response(
            LLMResponse(
                content="secret completion text",
                input_tokens=2000,
                output_tokens=800,
                model="gemini-2.5-flash-lite",
                provider="gemini",
            )
        )

    totals = await get_session_token_totals("sess-a")
    assert totals.run_count == 2
    assert totals.input_tokens == 3000
    assert totals.output_tokens == 1300
    assert totals.estimated_cost_usd > 0
    assert [run.step for run in totals.runs] == ["phase1", "phase2"]


@pytest.mark.asyncio
async def test_llm_run_log_emits_token_counts_only(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def _fake_info(_event: str, **kwargs: object) -> None:
        captured.append(kwargs)

    monkeypatch.setattr("app.llm.token_accounting.log.info", _fake_info)

    await record_llm_response(
        LLMResponse(
            content="prompt and completion must stay out of logs",
            input_tokens=42,
            output_tokens=7,
            model="gpt-4o-mini",
            provider="openai",
        ),
        step="job_fit",
        session_id="sess-b",
    )

    assert captured
    payload = captured[0]
    assert payload["input_tokens"] == 42
    assert payload["output_tokens"] == 7
    assert "content" not in payload
    assert "prompt and completion must stay out of logs" not in str(payload)
