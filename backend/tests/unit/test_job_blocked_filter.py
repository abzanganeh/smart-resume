"""Unit tests: blocked companies filtered from job results."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.jobs.filtering import filter_blocked_companies
from app.services.jobs.schemas import JobResult

pytestmark = pytest.mark.unit


def _job(company: str) -> JobResult:
    return JobResult(
        id=uuid4(),
        title="Engineer",
        company=company,
        posted_date=datetime.now(timezone.utc),
    )


def test_blocked_company_removed_from_live_and_cached_results() -> None:
    jobs = [
        _job("Acme Corp"),
        _job("Widget Inc"),
        _job("ACME CORP"),
    ]
    filtered = filter_blocked_companies(jobs, ["Acme Corp"])
    assert len(filtered) == 1
    assert filtered[0].company == "Widget Inc"
