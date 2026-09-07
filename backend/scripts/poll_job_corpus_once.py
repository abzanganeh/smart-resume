#!/usr/bin/env python3
"""Poll due global corpus companies once and upsert jobs into ``job_cache``.

Usage (from ``backend/``, or inside the staging backend container):

  uv run python scripts/poll_job_corpus_once.py
  uv run python scripts/poll_job_corpus_once.py --limit 80
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.db.engine import async_session_factory
from app.services.career_watch.poller import poll_due_companies


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max companies to poll this run (default: 50)",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if args.limit < 1:
        print("ERROR: --limit must be >= 1", file=sys.stderr)
        sys.exit(1)

    async with async_session_factory() as session:
        stats = await poll_due_companies(session, limit=args.limit)
        await session.commit()

    print("Job corpus poll complete")
    print(f"  companies_polled:       {stats.companies_polled}")
    print(f"  jobs_upserted:          {stats.jobs_upserted}")
    print(f"  failures:               {stats.failures}")
    print(f"  aggregators_polled:     {stats.aggregators_polled}")
    print(f"  aggregator_jobs_upserted: {stats.aggregator_jobs_upserted}")


if __name__ == "__main__":
    asyncio.run(main())
