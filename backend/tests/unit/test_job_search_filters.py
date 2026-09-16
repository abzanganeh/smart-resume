"""Unit tests for corpus job-search filter helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.jobs.job_service import (
    _DATE_POSTED_WINDOWS,
    _date_posted_cutoff,
    run_keyword_search,
)


def test_date_posted_cutoff_windows() -> None:
    now = datetime.now(timezone.utc)
    day_cutoff = _date_posted_cutoff("24h")
    week_cutoff = _date_posted_cutoff("week")
    month_cutoff = _date_posted_cutoff("month")

    assert day_cutoff is not None
    assert week_cutoff is not None
    assert month_cutoff is not None
    assert abs((now - day_cutoff) - _DATE_POSTED_WINDOWS["24h"]).total_seconds() < 2
    assert abs((now - week_cutoff) - _DATE_POSTED_WINDOWS["week"]).total_seconds() < 2
    assert abs((now - month_cutoff) - _DATE_POSTED_WINDOWS["month"]).total_seconds() < 2
    assert month_cutoff < week_cutoff < day_cutoff < now


def test_date_posted_cutoff_any_or_unknown() -> None:
    assert _date_posted_cutoff(None) is None
    assert _date_posted_cutoff("") is None
    assert _date_posted_cutoff("any") is None
    assert _date_posted_cutoff("invalid") is None
    assert _date_posted_cutoff(["week"]) is None


@pytest.mark.asyncio
async def test_run_keyword_search_allow_hirebase_false_empty_corpus() -> None:
    session = AsyncMock()
    with (
        patch.object(settings, "HIREBASE_API_KEY", "hb_test_key"),
        patch.object(settings, "JOB_SEARCH_DB_FIRST", True),
        patch.object(settings, "JOB_SEARCH_DB_MIN_RESULTS", 5),
        patch(
            "app.services.jobs.job_service.search_active_job_cache",
            new_callable=AsyncMock,
            return_value=([], 0),
        ),
        patch(
            "app.services.jobs.job_service.hirebase_client.search",
            new_callable=AsyncMock,
        ) as mock_hirebase,
        patch(
            "app.services.jobs.job_service.log_search",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.jobs.job_service.get_circuit_state",
            new_callable=AsyncMock,
        ) as mock_circuit,
    ):
        mock_circuit.return_value.is_open = False
        jobs, total, stale, message, charge, source = await run_keyword_search(
            session,
            user_id=uuid.uuid4(),
            query="software engineer",
            location=None,
            filters={},
            page=1,
            page_size=20,
            blocked_companies=[],
            allow_hirebase=False,
        )

    mock_hirebase.assert_not_awaited()
    assert jobs == []
    assert total == 0
    assert charge is False
    assert source == "corpus"
    assert message


@pytest.mark.asyncio
async def test_run_keyword_search_default_skips_hirebase() -> None:
    session = AsyncMock()
    with (
        patch.object(settings, "HIREBASE_API_KEY", "hb_test_key"),
        patch.object(settings, "JOB_SEARCH_DB_FIRST", False),
        patch(
            "app.services.jobs.job_service._corpus_only_search",
            new_callable=AsyncMock,
            return_value=([], 0, False, None, False, "corpus"),
        ) as mock_corpus_only,
        patch(
            "app.services.jobs.job_service.hirebase_client.search",
            new_callable=AsyncMock,
        ) as mock_hirebase,
    ):
        await run_keyword_search(
            session,
            user_id=uuid.uuid4(),
            query="software engineer",
            location=None,
            filters={},
            page=1,
            page_size=20,
            blocked_companies=[],
        )

    mock_corpus_only.assert_awaited()
    mock_hirebase.assert_not_awaited()
