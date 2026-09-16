"""Unit tests for corpus job-search filter helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.jobs.job_service import _date_posted_cutoff


def test_date_posted_cutoff_windows() -> None:
    now = datetime.now(timezone.utc)
    day_cutoff = _date_posted_cutoff("24h")
    week_cutoff = _date_posted_cutoff("week")
    month_cutoff = _date_posted_cutoff("month")

    assert day_cutoff is not None
    assert week_cutoff is not None
    assert month_cutoff is not None
    assert now - timedelta(days=1, hours=1) < day_cutoff <= now
    assert now - timedelta(days=8) < week_cutoff <= now
    assert now - timedelta(days=31) < month_cutoff <= now


def test_date_posted_cutoff_any_or_unknown() -> None:
    assert _date_posted_cutoff(None) is None
    assert _date_posted_cutoff("any") is None
    assert _date_posted_cutoff("invalid") is None
