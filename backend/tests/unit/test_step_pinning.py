"""Step pinning regression tests (M18 slice 4)."""

from __future__ import annotations

import pytest

from app.llm.model_registry import STEP_DEFAULTS, resolve_model


pytestmark = pytest.mark.unit


def test_checkup_is_pinned_to_cheap_gemini_flash_lite() -> None:
    provider, model = resolve_model("checkup")
    assert provider == "gemini"
    assert model == "gemini-3.5-flash-lite"


def test_phase3_rewrite_uses_mid_tier_flash_not_lite() -> None:
    """Phase 3 is the paid deliverable — pinned above flash-lite without downgrade."""
    provider, model = resolve_model("phase3_rewrite")
    assert provider == "gemini"
    assert model == "gemini-3.5-flash"
    assert model != STEP_DEFAULTS["phase1_keywords"][1]
