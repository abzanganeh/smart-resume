"""Unit tests for Hirebase-optional job search (M19 slice 1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.jobs.job_service import hirebase_is_configured, run_keyword_search
from app.services.jobs.schemas import JobResult


def test_hirebase_is_configured_requires_non_blank_key() -> None:
    with patch.object(settings, "HIREBASE_API_KEY", "  "):
        assert hirebase_is_configured() is False
    with patch.object(settings, "HIREBASE_API_KEY", "hb_test_key"):
        assert hirebase_is_configured() is True


@pytest.mark.asyncio
async def test_run_keyword_search_skips_hirebase_when_key_unset() -> None:
    job = JobResult(
        id=uuid.uuid4(),
        title="Backend Engineer",
        company="Stripe",
        location="SF",
        remote=False,
        salary_min_usd=None,
        salary_max_usd=None,
        employment_type="",
        posted_date=datetime.now(timezone.utc),
        description="python",
        apply_url="https://example.com/jobs/1",
        sources=["corpus"],
        score=None,
        first_seen_at=datetime.now(timezone.utc),
    )
    session = AsyncMock()
    with (
        patch.object(settings, "HIREBASE_API_KEY", ""),
        patch.object(settings, "JOB_SEARCH_DB_FIRST", True),
        patch.object(settings, "JOB_SEARCH_DB_MIN_RESULTS", 5),
        patch(
            "app.services.jobs.job_service.search_active_job_cache",
            new_callable=AsyncMock,
            return_value=([job], 1),
        ) as mock_corpus,
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
            query="python backend",
            location=None,
            filters={},
            page=1,
            page_size=20,
            blocked_companies=[],
            expand=False,
        )

    mock_corpus.assert_awaited()
    mock_hirebase.assert_not_awaited()
    assert source == "corpus"
    assert total == 1
    assert len(jobs) == 1
    assert stale is True
    assert message and "cached job corpus" in message
    assert charge is False
