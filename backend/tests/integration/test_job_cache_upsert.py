"""Integration tests for job_cache dedup upsert behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models.jobs import JobCache
from app.services.jobs.cache_writer import normalize_apify_record, upsert_job_cache

pytestmark = pytest.mark.integration


def _sample_raw(*, company: str = "Acme Corp", title: str = "Engineer") -> dict:
    return {
        "company": company,
        "title": title,
        "location": "Toronto, Canada",
        "postedDate": "2026-05-01T00:00:00Z",
        "id": "apify-1",
        "url": "https://example.com/jobs/1",
    }


@pytest.mark.asyncio
async def test_duplicate_dedup_key_upserts_instead_of_second_row(db_session) -> None:
    now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    record = normalize_apify_record(_sample_raw(), now=now)

    first = await upsert_job_cache(db_session, record)
    await db_session.commit()

    record2 = normalize_apify_record(
        {
            **_sample_raw(),
            "id": "apify-2",
            "description": "Updated description",
        },
        now=now,
    )
    second = await upsert_job_cache(db_session, record2)
    await db_session.commit()

    assert first.id == second.id
    assert second.description == "Updated description"
    assert "apify" in second.sources

    count = (
        await db_session.execute(select(func.count()).select_from(JobCache))
    ).scalar_one()
    assert count == 1
