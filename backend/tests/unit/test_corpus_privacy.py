"""Regression tests for shared corpus privacy (M19 slice 6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.career_watch import CareerAtsType, WatchedCompany
from app.services.career_watch.corpus_privacy import (
    assert_corpus_sources,
    sanitize_parsed_job_for_corpus,
    sanitize_raw_payload_for_corpus,
)
from app.services.career_watch.corpus_sync import _job_cache_record_from_poll
from app.services.career_watch.types import ParsedJob
from app.services.jobs.job_service import job_cache_to_result
from app.models.jobs import JobCache

pytestmark = pytest.mark.unit

_FORBIDDEN_RESULT_FIELDS = frozenset(
    {
        "user_id",
        "user_watched_company_id",
        "watch_id",
        "keywords",
        "raw_json",
    }
)


def test_sanitize_raw_payload_strips_user_scoped_keys() -> None:
    cleaned = sanitize_raw_payload_for_corpus(
        {
            "id": 1,
            "user_id": "secret",
            "keywords": ["python"],
            "title": "Engineer",
        }
    )
    assert cleaned == {"id": 1, "title": "Engineer"}


def test_assert_corpus_sources_drops_user_tags() -> None:
    assert assert_corpus_sources(["corpus", "user:abc", "watch:xyz"]) == ["corpus"]


def test_job_cache_record_from_poll_has_no_user_scoped_fields() -> None:
    company = WatchedCompany(
        id=uuid.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        careers_page_url="https://boards.greenhouse.io/acme",
        ats_type=CareerAtsType.greenhouse,
        ats_board_token="acme",
    )
    job = ParsedJob(
        external_job_id="100",
        title="Software Engineer",
        location="Remote",
        apply_url="https://boards.greenhouse.io/acme/jobs/100",
        description_text="Build things",
        posted_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
        raw_payload={
            "id": 100,
            "user_id": "must-not-leak",
            "keywords": ["secret"],
        },
    )
    record = _job_cache_record_from_poll(
        company,
        job,
        now=datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
    )
    assert record["sources"] == ["corpus"]
    assert "user_id" not in record["raw_json"]
    assert "keywords" not in record["raw_json"]
    assert "user_id" not in record


def test_job_cache_to_result_exposes_no_watchlist_fields() -> None:
    row = JobCache(
        id=uuid.uuid4(),
        title="Engineer",
        company="Acme",
        company_normalized="acme",
        location="Remote",
        remote=False,
        employment_type="",
        posted_date=datetime(2026, 8, 18, tzinfo=timezone.utc),
        description="Role",
        apply_url="https://example.com/jobs/1",
        dedup_key="dedup",
        expires_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        sources=["corpus"],
        external_ids={},
    )
    payload = job_cache_to_result(row).model_dump()
    assert _FORBIDDEN_RESULT_FIELDS.isdisjoint(payload.keys())


def test_sanitize_parsed_job_for_corpus_returns_new_job_when_dirty() -> None:
    original = ParsedJob(
        external_job_id="1",
        title="Engineer",
        location="Remote",
        apply_url="https://example.com",
        description_text="Role",
        posted_at=None,
        raw_payload={"user_id": "x"},
    )
    cleaned = sanitize_parsed_job_for_corpus(original)
    assert cleaned is not original
    assert "user_id" not in cleaned.raw_payload
