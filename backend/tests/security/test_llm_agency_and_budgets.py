"""Excessive agency and consumption bounds (M23 C1 / OWASP LLM03, LLM06).

The tailoring orchestrator is a fixed four-phase pipeline — no tool calling,
no autonomous retries beyond schema validation, no user-triggered phase jumps.
These tests verify that contract without editing ``agent/`` or ``llm/``
(M18 owns production hardening there).

Complements ``test_llm_injection_and_output.py`` (LLM01) and
``test_consumption_limits.py`` (LLM06 inventory).
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.orchestrator import run_phase
from app.llm.base import LLMClient
from app.main import app
from app.models.session import Session
from app.services.retrieval.exceptions import PromptBudgetExceededError

REPO_BACKEND = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_BACKEND / "app" / "agent"
ORCHESTRATOR = REPO_BACKEND / "app" / "agent" / "orchestrator.py"


def _orchestrator_phase_numbers() -> set[int]:
    """Extract literal phase numbers handled by ``run_phase``'s match block."""
    import re

    source = ORCHESTRATOR.read_text(encoding="utf-8")
    run_phase_block = source.split("async def run_phase(")[1].split("\nasync def ")[0]
    return {int(m) for m in re.findall(r"^\s*case\s+(\d+)\s*:", run_phase_block, re.MULTILINE)}


def test_orchestrator_only_runs_phases_one_through_four() -> None:
    """LLM03 — agency is bounded to the four shipped tailoring phases."""
    assert _orchestrator_phase_numbers() == {1, 2, 3, 4}


@pytest.mark.parametrize("invalid_phase", [0, 5, 99, -1])
async def test_orchestrator_rejects_unknown_phase(
    invalid_phase: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM03 — arbitrary phase numbers must not dispatch to hidden handlers."""
    from app.services import session_store

    monkeypatch.setattr(
        session_store,
        "acquire_phase_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        session_store,
        "get_session",
        AsyncMock(return_value=Session(session_id="agency-sess")),
    )
    monkeypatch.setattr(session_store, "update_phase_status", AsyncMock())
    monkeypatch.setattr(session_store, "release_phase_lock", AsyncMock())

    queue: asyncio.Queue = asyncio.Queue()
    llm = MagicMock(spec=LLMClient)
    llm.provider_name = "openai"
    llm.model_name = "gpt-4o-mini"

    with pytest.raises(ValueError, match="Unknown phase"):
        await run_phase("agency-sess", invalid_phase, llm, queue)


def test_agent_modules_do_not_expose_tool_calling_entry_points() -> None:
    """LLM03 — no ``run_tool`` / ``execute_tool`` surface in the agent package."""
    forbidden = {"run_tool", "execute_tool", "call_tool", "invoke_tool"}
    for py_file in AGENT_DIR.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden, (
                    f"{py_file.name} defines forbidden tool entry {node.name!r}"
                )


def test_system_prompts_forbid_fabrication_and_unbounded_action() -> None:
    """LLM03/LLM07 — operator prompts stay conservative; no open-ended agency."""
    prompts_dir = AGENT_DIR / "prompts"
    system_base = (prompts_dir / "system_base.txt").read_text(encoding="utf-8").lower()
    assert "never fabricate" in system_base
    assert "metrics_needed" in system_base
    phase3 = (prompts_dir / "phase3.txt").read_text(encoding="utf-8").lower()
    assert "never fabricate" in phase3


@pytest.mark.asyncio
async def test_prompt_budget_exceeded_emits_422_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM06 — retrieval prompt budget failures fail closed with a bounded error."""
    from app.services import session_store

    session = Session(session_id="budget-sess")
    monkeypatch.setattr(
        session_store,
        "acquire_phase_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        session_store,
        "get_session",
        AsyncMock(return_value=session),
    )
    monkeypatch.setattr(
        session_store,
        "update_phase_status",
        AsyncMock(),
    )
    monkeypatch.setattr(
        session_store,
        "release_phase_lock",
        AsyncMock(),
    )

    async def _raise_budget(*_args, **_kwargs):
        raise PromptBudgetExceededError(
            total_tokens=200_000, budget=120_000, model="gpt-4o-mini"
        )

    monkeypatch.setattr(
        "app.agent.phase3_rewrite.run",
        _raise_budget,
    )

    queue: asyncio.Queue = asyncio.Queue()
    llm = MagicMock(spec=LLMClient)
    llm.provider_name = "openai"
    llm.model_name = "gpt-4o-mini"

    with pytest.raises(PromptBudgetExceededError):
        await run_phase("budget-sess", 3, llm, queue)

    events = []
    while not queue.empty():
        events.append(await queue.get())

    error_events = [e for e in events if e.get("event") == "error"]
    assert error_events, "orchestrator must emit an error SSE event"
    assert error_events[-1]["status"] == 422
    assert error_events[-1]["code"] == "prompt_budget_exceeded"


def test_orchestrator_prompt_budget_handler_is_wired() -> None:
    """LLM06 — budget exception path is explicit in orchestrator source."""
    source = inspect.getsource(run_phase)
    assert "PromptBudgetExceededError" in source
    assert "prompt_budget_exceeded" in source


@pytest.mark.asyncio
async def test_phase_events_cannot_start_a_pipeline_run() -> None:
    """LLM06 — SSE stream must not reach the provider without ``phases/run``."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/sessions")
        assert created.status_code == 201, created.text
        session_id = created.json()["session_id"]

        events = await client.get(f"/api/sessions/{session_id}/phases/1/events")
        assert events.status_code == 409, (
            "phase events must not start a run without phases/{phase}/run, "
            f"got {events.status_code} {events.text[:200]}"
        )
