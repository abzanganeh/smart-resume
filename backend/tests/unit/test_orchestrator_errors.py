"""Orchestrator error classification for LLM provider failures."""

from app.agent.orchestrator import _classify_error, _user_facing_error


def test_classify_openrouter_402_as_insufficient_credits() -> None:
    exc = RuntimeError("OpenRouter 402: not enough credits")
    assert _classify_error(exc) == "llm_insufficient_credits"
    assert "402" in _user_facing_error(exc) or "credits" in _user_facing_error(exc).lower()
