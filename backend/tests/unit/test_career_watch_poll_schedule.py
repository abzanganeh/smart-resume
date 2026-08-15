"""Unit tests for Career Watch poll scheduling helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.billing.tier_limits import get_seed_rows
from app.services.career_watch.poll_schedule import (
    interval_for_plan_code,
    is_poll_due,
    min_interval_for_plan_codes,
)

pytestmark = pytest.mark.unit


def _interval_map() -> dict[str, int]:
    return {row["plan_code"]: row["career_watch_interval_minutes"] for row in get_seed_rows()}


def test_min_interval_uses_fastest_watcher_tier() -> None:
    intervals = _interval_map()
    result = min_interval_for_plan_codes(
        ["free", "monthly_premium"],
        intervals,
    )
    assert result == intervals["monthly_premium"]


def test_min_interval_empty_returns_none() -> None:
    assert min_interval_for_plan_codes([], _interval_map()) is None


def test_interval_for_plan_code_falls_back_to_free() -> None:
    intervals = _interval_map()
    assert interval_for_plan_code("unknown_plan", intervals) == intervals["free"]


def test_is_poll_due_when_never_polled() -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    assert is_poll_due(None, 15, now=now) is True


def test_is_poll_due_respects_interval() -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(minutes=10)
    assert is_poll_due(last, 15, now=now) is False
    assert is_poll_due(last, 5, now=now) is True


def test_plus_tier_interval_is_five_minutes() -> None:
    intervals = _interval_map()
    assert intervals["monthly_plus"] == 5
    assert intervals["monthly_pro"] == 15
