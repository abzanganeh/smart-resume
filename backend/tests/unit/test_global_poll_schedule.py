"""Unit tests for global seed poll scheduling (slice 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.career_watch.global_poll_schedule import interval_minutes_for_tier
from app.services.career_watch.poll_schedule import is_poll_due

pytestmark = pytest.mark.unit


def test_interval_minutes_for_tier_defaults() -> None:
    assert interval_minutes_for_tier(1) == 15
    assert interval_minutes_for_tier(2) == 30
    assert interval_minutes_for_tier(3) == 45
    assert interval_minutes_for_tier(None) == 30


@pytest.mark.parametrize(
    ("tier", "minutes_ago", "expected_due"),
    [
        (1, 20, True),
        (1, 10, False),
        (2, 35, True),
        (2, 20, False),
        (3, 50, True),
        (3, 30, False),
    ],
)
def test_global_tier_due_logic(
    tier: int, minutes_ago: int, expected_due: bool
) -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(minutes=minutes_ago)
    interval = interval_minutes_for_tier(tier)
    assert is_poll_due(last, interval, now=now) is expected_due


def test_never_polled_is_due() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    assert is_poll_due(None, interval_minutes_for_tier(1), now=now) is True
