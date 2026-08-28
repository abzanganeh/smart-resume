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


def test_free_tier_registration_grant_is_three_credits() -> None:
    """Free tier grants 3 tailored-resume credits (also caps cover letters)."""
    free = seed_row_for_plan("free")
    assert free is not None
    assert free["resumes_per_period"] == 3
    assert free["cover_letters_per_period"] == 3


def test_premium_tracker_active_limit_is_capped() -> None:
    """Premium is "unlimited" in marketing copy but carries a 250-row soft cap
    on the tracker to prevent runaway growth."""
    for plan in ("monthly_premium", "yearly_premium"):
        row = seed_row_for_plan(plan)
        assert row is not None, plan
        assert row["tracker_active_limit"] == 250, plan


def test_pro_and_plus_tracker_limits_stay_unlimited() -> None:
    """Pro / Plus tiers do not cap active tracker slots."""
    for plan in ("monthly_pro", "yearly_pro", "monthly_plus", "yearly_plus"):
        row = seed_row_for_plan(plan)
        assert row is not None, plan
        assert row["tracker_active_limit"] is None, plan


def test_free_tier_tracker_active_limit_is_ten() -> None:
    """Free tier's active-slot cap sits above its per-period credit count so
    the counter — not the tracker — is the binding constraint."""
    free = seed_row_for_plan("free")
    assert free is not None
    assert free["tracker_active_limit"] == 10
