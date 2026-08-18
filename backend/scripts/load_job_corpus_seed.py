#!/usr/bin/env python3
"""Load TalioCV job corpus seed rows into ``watched_companies``.

Usage (from ``backend/``):

  uv run python scripts/load_job_corpus_seed.py
  uv run python scripts/load_job_corpus_seed.py --seed path/to/seed_500.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.db.engine import async_session_factory
from app.services.career_watch.job_corpus_seed import load_seed_file

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = BACKEND_ROOT / "data" / "job_corpus" / "seed_500.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        type=Path,
        default=DEFAULT_SEED,
        help=f"Seed JSON path (default: {DEFAULT_SEED})",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if not args.seed.is_file():
        print(f"ERROR: seed file not found: {args.seed}", file=sys.stderr)
        sys.exit(1)

    async with async_session_factory() as session:
        stats = await load_seed_file(session, args.seed)
        await session.commit()

    print("Job corpus seed load complete")
    print(f"  inserted: {stats.inserted}")
    print(f"  updated:  {stats.updated}")


if __name__ == "__main__":
    asyncio.run(main())
