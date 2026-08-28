"""GEMINI_API_KEY alias for GOOGLE_API_KEY."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_gemini_api_key_aliases_to_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    s = Settings()
    assert s.GOOGLE_API_KEY == "test-gemini-key"


def test_google_api_key_takes_precedence_over_gemini_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "primary-key")
    monkeypatch.setenv("GEMINI_API_KEY", "alias-key")
    s = Settings()
    assert s.GOOGLE_API_KEY == "primary-key"
