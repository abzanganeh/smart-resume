#!/usr/bin/env python3
"""Migrate legacy subscribers to the 2026 pricing restructure plan codes.

Usage (from ``backend/``):

  uv run python scripts/migrate_subscribers.py              # dry-run (default)
  uv run python scripts/migrate_subscribers.py --apply      # commit DB changes
  uv run python scripts/migrate_subscribers.py --apply --sync-stripe

Maps ``daily`` → ``weekly``, ``monthly`` → ``monthly_pro`` / ``yearly_pro``,
expires LLM add-on subscriptions, and zeros ``better`` / ``best`` credits.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.db.engine import async_session_factory
from app.services.billing.subscriber_migration import run_subscriber_migration


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist migration changes (default is dry-run).",
    )
    parser.add_argument(
        "--sync-stripe",
        action="store_true",
        help="Push price updates to Stripe when --apply is set.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    dry_run = not args.apply

    async with async_session_factory() as session:
        stats = await run_subscriber_migration(
            session,
            dry_run=dry_run,
            sync_stripe=args.sync_stripe and not dry_run,
        )
        if not dry_run:
            await session.commit()

    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"[{mode}] subscriber migration complete")
    print(f"  base_plans_updated:      {stats.base_plans_updated}")
    print(f"  daily_to_weekly:         {stats.daily_to_weekly}")
    print(f"  monthly_to_pro:          {stats.monthly_to_pro}")
    print(f"  addons_expired:          {stats.addons_expired}")
    print(f"  credits_expired:         {stats.credits_expired}")
    print(f"  skipped_already_migrated:{stats.skipped_already_migrated}")
    if args.sync_stripe and not dry_run:
        print(f"  stripe_synced:           {stats.stripe_synced}")
        if stats.stripe_errors:
            print("  stripe_errors:")
            for err in stats.stripe_errors:
                print(f"    - {err}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
