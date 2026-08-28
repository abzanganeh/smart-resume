"""Contract tests tying staging-smoke.sh assertions to seed tier data.

These values are checked by ``scripts/staging-smoke.sh`` after deploy.
If you change free registration grants or tracker caps, update both places.
"""

from __future__ import annotations

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
