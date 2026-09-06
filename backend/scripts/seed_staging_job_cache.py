#!/usr/bin/env python3
"""Insert idempotent sample ``job_cache`` rows for local staging smoke and UI.

Without cached rows, corpus search returns HTTP 200 with an empty outage message
when Hirebase is unset. This script is safe to re-run (upserts by dedup_key).

Usage (from ``backend/`` or via docker exec):

  uv run python scripts/seed_staging_job_cache.py
"""

from __future__ import annotations

import asyncio
import sys

from app.db.engine import async_session_factory
from app.services.jobs.cache_writer import normalize_apify_record, upsert_job_cache

# Enough variety to satisfy keyword search for common onboarding titles.
_SAMPLE_JOBS: tuple[dict[str, str], ...] = (
    {
        "company": "Stripe",
        "title": "Software Engineer",
        "location": "San Francisco, CA",
        "description": "Software engineer role building APIs with Python and distributed systems.",
        "url": "https://boards.greenhouse.io/stripe/jobs/staging-smoke-1",
        "id": "staging-smoke-1",
    },
    {
        "company": "Databricks",
        "title": "Senior Software Engineer",
        "location": "Remote",
        "remote": "true",
        "description": "Senior software engineer working on data platform services in Python.",
        "url": "https://boards.greenhouse.io/databricks/jobs/staging-smoke-2",
        "id": "staging-smoke-2",
    },
    {
        "company": "Figma",
        "title": "Backend Engineer",
        "location": "New York, NY",
        "description": "Backend engineer building reliable services for collaborative design tools.",
        "url": "https://boards.greenhouse.io/figma/jobs/staging-smoke-3",
        "id": "staging-smoke-3",
    },
    {
        "company": "Airbnb",
        "title": "Software Engineer, Platform",
        "location": "Remote",
        "remote": "true",
        "description": "Platform software engineer improving search and booking infrastructure.",
        "url": "https://boards.greenhouse.io/airbnb/jobs/staging-smoke-4",
        "id": "staging-smoke-4",
    },
    {
        "company": "Coinbase",
        "title": "Software Engineer",
        "location": "Remote",
        "remote": "true",
        "description": "Software engineer building secure financial systems at scale.",
        "url": "https://boards.greenhouse.io/coinbase/jobs/staging-smoke-5",
        "id": "staging-smoke-5",
    },
    {
        "company": "OpenAI",
        "title": "Machine Learning Engineer",
        "location": "San Francisco, CA",
        "description": "ML engineer improving model training and inference pipelines.",
        "url": "https://jobs.ashbyhq.com/openai/staging-smoke-6",
        "id": "staging-smoke-6",
    },
)


async def seed_staging_job_cache() -> int:
    """Upsert sample rows; returns number of rows touched."""
    touched = 0
    async with async_session_factory() as session:
        for raw in _SAMPLE_JOBS:
            record = normalize_apify_record(
                {
                    "company": raw["company"],
                    "title": raw["title"],
                    "location": raw.get("location", ""),
                    "remote": raw.get("remote") == "true",
                    "description": raw["description"],
                    "url": raw["url"],
                    "id": raw["id"],
                },
                source="corpus",
                ttl_seconds=30 * 24 * 3600,
            )
            record["is_active"] = True
            await upsert_job_cache(session, record)
            touched += 1
        await session.commit()
    return touched


async def main() -> None:
    count = await seed_staging_job_cache()
    print(f"Staging job_cache seed complete ({count} sample rows upserted)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
