"""Tier limits config — seed data and lookup helpers."""

from __future__ import annotations

import pytest

from app.services.billing.tier_limits import (
    CANONICAL_PLAN_CODES,
    get_seed_rows,
    seed_row_for_plan,
)


pytestmark = pytest.mark.unit


def test_canonical_plan_codes_include_all_tiers() -> None:
    assert "free" in CANONICAL_PLAN_CODES
    assert "weekly" in CANONICAL_PLAN_CODES
    assert "monthly_pro" in CANONICAL_PLAN_CODES
    assert "monthly_premium" in CANONICAL_PLAN_CODES


def test_seed_rows_cover_every_canonical_plan() -> None:
    rows = get_seed_rows()
    codes = {r["plan_code"] for r in rows}
    assert codes == set(CANONICAL_PLAN_CODES)


def test_free_tier_has_no_whisper() -> None:
    free = seed_row_for_plan("free")
    assert free is not None
    assert free["whisper_enabled"] is False
    assert free["whisper_uses_per_period"] == 0


def test_weekly_tier_whisper_limit() -> None:
    weekly = seed_row_for_plan("weekly")
    assert weekly is not None
    assert weekly["whisper_enabled"] is True
    assert weekly["whisper_uses_per_period"] == 2


def test_pro_tier_resume_and_cover_letter_match() -> None:
    pro = seed_row_for_plan("monthly_pro")
    assert pro is not None
    assert pro["resumes_per_period"] == 50
    assert pro["cover_letters_per_period"] == 50


def test_premium_soft_cap() -> None:
    premium = seed_row_for_plan("monthly_premium")
    assert premium is not None
    assert premium["resumes_per_period"] == 300
    assert premium["soft_cap_message"]
