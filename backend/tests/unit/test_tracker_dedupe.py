"""Unit tests for the tracker duplicate-detection helper (B3)."""

from __future__ import annotations

import pytest

from app.services.tracker import normalize_for_dedupe

pytestmark = pytest.mark.unit


class TestNormalizeForDedupe:
    def test_lowercases_and_collapses_punctuation(self) -> None:
        assert (
            normalize_for_dedupe("Google, Inc.")
            == normalize_for_dedupe("google inc")
            == "google inc"
        )

    def test_collapses_repeated_spaces(self) -> None:
        assert normalize_for_dedupe("Senior   Software    Engineer") == (
            "senior software engineer"
        )

    def test_strips_trailing_punctuation(self) -> None:
        assert normalize_for_dedupe("Meta!") == "meta"

    def test_handles_none_and_empty(self) -> None:
        assert normalize_for_dedupe(None) == ""
        assert normalize_for_dedupe("") == ""
        assert normalize_for_dedupe("   ") == ""

    def test_returns_original_alphanumerics_untouched(self) -> None:
        assert normalize_for_dedupe("PM 2 (New York)") == "pm 2 new york"

    def test_unicode_letters_dropped(self) -> None:
        # ASCII-only normalization is intentional so we don't false-match
        # multilingual variants (e.g. "Café" ≠ "Cafe" here).  If we ever
        # need locale-aware collation we'd swap this for icu.
        assert normalize_for_dedupe("Café") == "caf"
