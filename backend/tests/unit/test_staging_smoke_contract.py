"""Contract tests tying staging-smoke.sh assertions to seed tier data.

These values are checked by ``scripts/staging-smoke.sh`` after deploy.
If you change free registration grants or tracker caps, update both places.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.billing.tier_limits import seed_row_for_plan

pytestmark = pytest.mark.unit

# Seed values checked by staging-smoke.sh (B4+). Register credits in smoke
# compare against GET /api/billing/free-tier starting_credits, not a literal here.
EXPECTED_FREE_STARTING_CREDITS = 3
EXPECTED_FREE_TRACKER_ACTIVE_LIMIT = 10


def test_staging_smoke_free_tier_starting_credits() -> None:
    row = seed_row_for_plan("free")
    assert row is not None
    assert row["resumes_per_period"] == EXPECTED_FREE_STARTING_CREDITS
    assert row["cover_letters_per_period"] == EXPECTED_FREE_STARTING_CREDITS


def test_staging_smoke_free_tier_tracker_active_limit() -> None:
    row = seed_row_for_plan("free")
    assert row is not None
    assert row["tracker_active_limit"] == EXPECTED_FREE_TRACKER_ACTIVE_LIMIT


def test_staging_smoke_script_includes_verify_unlock_flow() -> None:
    """CI does not run staging-smoke.sh — grep guards the verify gate contract."""
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "staging-smoke.sh"
    )
    text = script.read_text()
    required = (
        "REQUIRE_MAILPIT",
        "/api/v1/search",
        "/api/auth/verify/",
        "spendable_credit_balance",
        "email_verified_at",
        "upgrade-insecure-requests",
    )
    for needle in required:
        assert needle in text, f"staging-smoke.sh must contain {needle!r}"
