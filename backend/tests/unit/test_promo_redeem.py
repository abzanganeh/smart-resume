"""Unit tests for promo code normalization and timing-safe compare."""

from __future__ import annotations

import pytest

from app.services.billing.promo import (
    codes_match,
    normalize_promo_code,
)


def test_normalize_promo_code_uppercases_and_trims() -> None:
    assert normalize_promo_code("  save10  ") == "SAVE10"


def test_normalize_promo_code_empty_after_trim() -> None:
    assert normalize_promo_code("   ") == ""


def test_codes_match_equal() -> None:
    assert codes_match("SAVE10", "SAVE10") is True


def test_codes_match_rejects_mismatch() -> None:
    assert codes_match("SAVE10", "SAVE11") is False


def test_codes_match_rejects_different_lengths() -> None:
    assert codes_match("SAVE10", "SAVE1") is False
