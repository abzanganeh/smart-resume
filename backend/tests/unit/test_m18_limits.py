"""Token ceiling and checkup limit tests (M18 slices 5–6)."""

from __future__ import annotations

import pytest

from app.config import settings
from app.llm.base import LLMResponse
from app.llm.token_accounting import (
    SessionTokenBudgetExceeded,
    clear_session_token_totals,
    record_llm_response,
)
from app.models.qa import QAOutput
from app.services.checkup_limits import (
    checkup_device_counter_key,
    checkup_result_cache_key,
    enforce_anonymous_checkup_device_cap,
    load_cached_checkup_result,
    store_cached_checkup_result,
)


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def _reset_usage() -> None:
    await clear_session_token_totals("ceil-session")


@pytest.mark.asyncio
async def test_record_llm_response_raises_when_session_exceeds_token_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SESSION_LLM_TOKEN_CEILING", 1000)

    response_small = LLMResponse(
        content="x",
        input_tokens=400,
        output_tokens=300,
        model="gemini-2.5-flash-lite",
        provider="gemini",
    )
    response_large = LLMResponse(
        content="y",
        input_tokens=200,
        output_tokens=200,
        model="gemini-2.5-flash-lite",
        provider="gemini",
    )
    await record_llm_response(response_small, step="phase1", session_id="ceil-session")
    with pytest.raises(SessionTokenBudgetExceeded):
        await record_llm_response(response_large, step="phase1", session_id="ceil-session")


def test_checkup_cache_key_is_stable() -> None:
    a = checkup_result_cache_key(resume_text="resume", jd_text="jd")
    b = checkup_result_cache_key(resume_text="resume", jd_text="jd")
    assert a == b
    assert a.startswith("checkup:result:")


@pytest.mark.asyncio
async def test_checkup_result_cache_round_trip() -> None:
    result = QAOutput(
        checklist=[],
        overall_status="pass",
        user_action_required=[],
        ats_score=72,
        score_ceiling=85,
        blocking_issues=[],
        quick_wins=[],
        score_axes=[],
    )
    key = checkup_result_cache_key(resume_text="r", jd_text="j")
    await store_cached_checkup_result(key, result)
    loaded = await load_cached_checkup_result(key)
    assert loaded is not None
    assert loaded.ats_score == 72


@pytest.mark.asyncio
async def test_anonymous_checkup_device_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHECKUP_DEVICE_DAILY_LIMIT", 2)
    await enforce_anonymous_checkup_device_cap(user_agent="ua", client_ip="1.2.3.4")
    await enforce_anonymous_checkup_device_cap(user_agent="ua", client_ip="1.2.3.4")
    with pytest.raises(ValueError, match="checkup_device_daily_limit"):
        await enforce_anonymous_checkup_device_cap(user_agent="ua", client_ip="1.2.3.4")


def test_checkup_device_counter_key_includes_day() -> None:
    key = checkup_device_counter_key(user_agent="Mozilla", client_ip="127.0.0.1")
    assert key.startswith("checkup:device:")
