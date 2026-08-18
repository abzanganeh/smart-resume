"""Job corpus global seed schema (slice 0 — job-corpus-a-b)."""

from __future__ import annotations

import pytest
from sqlalchemy import Index

from app.db.base import Base
from app.models.career_watch import WatchedCompany
from app.models.jobs import JobCache

pytestmark = pytest.mark.unit


def test_watched_company_global_seed_columns() -> None:
    cols = {c.name for c in WatchedCompany.__table__.columns}
    assert "is_global_seed" in cols
    assert "poll_priority_tier" in cols


def test_job_cache_corpus_tracking_columns() -> None:
    cols = {c.name for c in JobCache.__table__.columns}
    for name in (
        "first_seen_at",
        "last_seen_at",
        "is_active",
        "apply_url_normalized",
        "ats_type",
        "external_job_id",
    ):
        assert name in cols, f"job_cache missing column {name}"


def test_job_cache_active_first_seen_index() -> None:
    indexes = JobCache.__table__.indexes
    match = [
        idx
        for idx in indexes
        if isinstance(idx, Index)
        and idx.name == "ix_job_cache_active_first_seen"
        and [c.name for c in idx.columns] == ["is_active", "first_seen_at"]
    ]
    assert match, "expected ix_job_cache_active_first_seen on (is_active, first_seen_at)"


def test_job_corpus_tables_in_metadata() -> None:
    assert "watched_companies" in Base.metadata.tables
    assert "job_cache" in Base.metadata.tables
