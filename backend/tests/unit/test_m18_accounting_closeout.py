"""Regression tests for full LLM cost accounting (M18 follow-up)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.base import LLMClient, LLMMessage, LLMResponse
from app.llm.model_registry import STEP_DEFAULTS
from app.llm.pricing import has_price_row
from app.llm.token_accounting import (
    clear_platform_token_totals,
    clear_session_token_totals,
    clear_user_token_totals,
    get_platform_token_totals,
    get_user_token_totals,
    llm_accounting_context,
    record_llm_response,
)
from app.llm.tracking_client import TrackingLLMClient


pytestmark = pytest.mark.unit

_CHECKUP_ROUTER = (
    Path(__file__).resolve().parents[2] / "app" / "routers" / "checkup.py"
).read_text(encoding="utf-8")


class _FakeLLMClient(LLMClient):
    def __init__(self) -> None:
        self.last_stream_input_tokens = 12
        self.last_stream_output_tokens = 8

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        return LLMResponse(
            content="ok",
            input_tokens=10,
            output_tokens=5,
            model="gemini-2.5-flash-lite",
            provider="gemini",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ):
        yield "hello"

    @property
    def context_window(self) -> int:
        return 4096

    @property
    def supports_structured_output(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return "gemini-2.5-flash-lite"


@pytest.fixture(autouse=True)
async def _reset_usage() -> None:
    await clear_session_token_totals("acct-session")
    await clear_user_token_totals("user-1")
    await clear_platform_token_totals()


@pytest.mark.asyncio
async def test_record_llm_response_always_writes_platform_ledger() -> None:
    response = LLMResponse(
        content="x",
        input_tokens=100,
        output_tokens=50,
        model="gemini-2.5-flash-lite",
        provider="gemini",
    )
    await record_llm_response(response, step="checkup", user_id="anonymous")

    platform = await get_platform_token_totals()
    assert platform.run_count == 1
    assert platform.input_tokens == 100
    assert platform.output_tokens == 50
    assert platform.estimated_cost_usd > 0


@pytest.mark.asyncio
async def test_record_llm_response_writes_user_and_session_ledgers() -> None:
    response = LLMResponse(
        content="x",
        input_tokens=40,
        output_tokens=20,
        model="gemini-2.5-flash-lite",
        provider="gemini",
    )
    with llm_accounting_context("acct-session", "chat", user_id="user-1"):
        await record_llm_response(response)

    user_totals = await get_user_token_totals("user-1")
    assert user_totals.run_count == 1
    assert user_totals.input_tokens == 40

    platform = await get_platform_token_totals()
    assert platform.run_count == 1


def test_every_registry_step_model_has_price_row() -> None:
    missing: list[str] = []
    for step, (provider, model) in STEP_DEFAULTS.items():
        if not has_price_row(provider, model):
            missing.append(f"{step} -> {provider}/{model}")
    assert not missing, "Missing pricing rows: " + "; ".join(missing)


def test_checkup_router_pins_checkup_step_and_skips_narrative() -> None:
    assert 'get_llm_client_for_step("checkup")' in _CHECKUP_ROUTER
    assert "include_narrative=False" in _CHECKUP_ROUTER


@pytest.mark.asyncio
async def test_tracking_client_records_stream_usage() -> None:
    client = TrackingLLMClient(_FakeLLMClient())
    chunks: list[str] = []
    async for chunk in client.stream([LLMMessage(role="user", content="hi")]):
        chunks.append(chunk)

    assert chunks == ["hello"]
    platform = await get_platform_token_totals()
    assert platform.run_count == 1
    assert platform.input_tokens == 12
    assert platform.output_tokens == 8
