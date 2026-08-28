"""Orchestrator error classification for LLM provider failures."""

from app.agent.orchestrator import _classify_error, _user_facing_error
from app.services.billing.exceptions import FreeTierAiBudgetExceededError


def test_classify_openrouter_402_as_insufficient_credits() -> None:
    exc = RuntimeError("OpenRouter 402: not enough credits")
    assert _classify_error(exc) == "llm_insufficient_credits"
    assert "402" in _user_facing_error(exc) or "credits" in _user_facing_error(exc).lower()


def test_classify_free_tier_cap_is_not_platform_credit_outage() -> None:
    exc = FreeTierAiBudgetExceededError(cap_usd=0.03, used_usd=0.03)
    assert _classify_error(exc) == "free_tier_ai_cap_reached"
    assert "retrying will not help" in _user_facing_error(exc).lower()
