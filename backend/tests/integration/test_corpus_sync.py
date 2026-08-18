"""Integration tests for corpus_sync (slice 2 — job-corpus-a-b)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.career_watch import CareerAtsType, CareerJobCache, WatchedCompany
from app.models.jobs import JobCache
from app.services.career_watch.corpus_sync import sync_polled_jobs_to_caches
from app.services.career_watch.types import ParsedJob

pytestmark = pytest.mark.integration


async def _seed_company(db_session) -> WatchedCompany:
    company = WatchedCompany(
        id=uuid.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        careers_page_url="https://boards.greenhouse.io/acme",
        ats_type=CareerAtsType.greenhouse,
        ats_board_token="acme",
        is_global_seed=True,
        poll_priority_tier=1,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest.mark.asyncio
async def test_sync_polled_jobs_upserts_both_caches(db_session) -> None:
    company = await _seed_company(db_session)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    jobs = [
        ParsedJob(
            external_job_id="100",
            title="Software Engineer",
            location="San Francisco, CA",
            apply_url="https://boards.greenhouse.io/acme/jobs/100",
            description_text="Build things",
            posted_at=now,
            raw_payload={"id": 100},
        )
    ]
    inserted = await sync_polled_jobs_to_caches(db_session, company, jobs, now=now)
    await db_session.commit()

    assert inserted == 1
    career = (
        await db_session.execute(
            select(CareerJobCache).where(
                CareerJobCache.watched_company_id == company.id
            )
        )
    ).scalar_one()
    assert career.title == "Software Engineer"
    assert career.is_open is True

    job_cache = (await db_session.execute(select(JobCache))).scalar_one()
    assert job_cache.company == "Acme Corp"
    assert job_cache.is_active is True
    assert job_cache.first_seen_at == now
    assert job_cache.external_job_id == "100"
    assert "corpus" in job_cache.sources


@pytest.mark.asyncio
async def test_sync_polled_jobs_tombstones_missing_roles(db_session) -> None:
    company = await _seed_company(db_session)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    initial = [
        ParsedJob(
            external_job_id="100",
            title="Role A",
            location="Remote",
            apply_url="https://boards.greenhouse.io/acme/jobs/100",
            description_text="A",
            posted_at=now,
            raw_payload={"id": 100},
        ),
        ParsedJob(
            external_job_id="200",
            title="Role B",
            location="Remote",
            apply_url="https://boards.greenhouse.io/acme/jobs/200",
            description_text="B",
            posted_at=now,
            raw_payload={"id": 200},
        ),
    ]
    await sync_polled_jobs_to_caches(db_session, company, initial, now=now)
    await db_session.commit()

    refreshed = [
        ParsedJob(
            external_job_id="100",
            title="Role A",
            location="Remote",
            apply_url="https://boards.greenhouse.io/acme/jobs/100",
            description_text="A",
            posted_at=now,
            raw_payload={"id": 100},
        ),
    ]
    await sync_polled_jobs_to_caches(db_session, company, refreshed, now=now)
    await db_session.commit()

    stale = (
        await db_session.execute(
            select(CareerJobCache).where(CareerJobCache.external_job_id == "200")
        )
    ).scalar_one()
    assert stale.is_open is False

    stale_cache = (
        await db_session.execute(
            select(JobCache).where(JobCache.external_job_id == "200")
        )
    ).scalar_one()
    assert stale_cache.is_active is False
