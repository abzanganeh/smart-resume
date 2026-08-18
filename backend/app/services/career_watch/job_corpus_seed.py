"""TalioCV job corpus seed validation and idempotent loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import CareerAtsType, WatchedCompany

VALID_ATS_TYPES: frozenset[str] = frozenset({"greenhouse", "lever", "ashby"})
TIER_TARGETS: dict[int, int] = {1: 100, 2: 175, 3: 225}
TOTAL_TARGET = 500
REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "slug",
    "ats_type",
    "ats_board_token",
    "poll_priority_tier",
    "careers_page_url",
)


def careers_page_url(ats_type: str, board_token: str) -> str:
    """Build the public careers board URL for a supported ATS."""
    token = board_token.strip()
    if ats_type == "greenhouse":
        return f"https://boards.greenhouse.io/{token}"
    if ats_type == "lever":
        return f"https://jobs.lever.co/{token}"
    if ats_type == "ashby":
        return f"https://jobs.ashbyhq.com/{token}"
    raise ValueError(f"unsupported ats_type: {ats_type}")


def read_seed_json(path: Path) -> list[dict[str, Any]]:
    """Load seed rows from ``path``."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("seed file must be a JSON array")
    return raw


def tier_counts(records: list[dict[str, Any]]) -> dict[int, int]:
    counts = {1: 0, 2: 0, 3: 0}
    for row in records:
        tier = row.get("poll_priority_tier")
        if tier in counts:
            counts[int(tier)] += 1
    return counts


def validate_seed_records(
    records: list[dict[str, Any]],
    *,
    require_full_corpus: bool = True,
) -> None:
    """Validate seed corpus invariants; raise ``ValueError`` on failure."""
    if require_full_corpus and len(records) != TOTAL_TARGET:
        raise ValueError(f"expected {TOTAL_TARGET} rows, got {len(records)}")
    if not require_full_corpus and not records:
        raise ValueError("seed records must not be empty")

    if require_full_corpus:
        counts = tier_counts(records)
        for tier, target in TIER_TARGETS.items():
            if counts[tier] != target:
                raise ValueError(
                    f"tier {tier}: expected {target} rows, got {counts[tier]}"
                )

    slugs: set[str] = set()
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"row {index} is not an object")

        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            raise ValueError(f"row {index} missing fields: {', '.join(missing)}")

        slug = str(row["slug"]).strip().lower()
        if slug != row["slug"]:
            raise ValueError(f"row {index} slug must be lowercase: {row['slug']!r}")
        if slug in slugs:
            raise ValueError(f"duplicate slug: {slug}")
        slugs.add(slug)

        ats_type = row["ats_type"]
        if ats_type not in VALID_ATS_TYPES:
            raise ValueError(f"row {index} invalid ats_type: {ats_type!r}")

        tier = row["poll_priority_tier"]
        if tier not in TIER_TARGETS:
            raise ValueError(f"row {index} invalid poll_priority_tier: {tier!r}")

        token = str(row["ats_board_token"]).strip()
        if not token:
            raise ValueError(f"row {index} empty ats_board_token")

        expected_url = careers_page_url(ats_type, token)
        if row["careers_page_url"] != expected_url:
            raise ValueError(
                f"row {index} careers_page_url mismatch for {slug}: "
                f"expected {expected_url!r}, got {row['careers_page_url']!r}"
            )


@dataclass(frozen=True)
class LoadStats:
    inserted: int = 0
    updated: int = 0


def _row_to_company(row: dict[str, Any], *, existing: WatchedCompany | None) -> WatchedCompany:
    if existing is None:
        company = WatchedCompany(
            name=str(row["name"]),
            slug=str(row["slug"]),
            careers_page_url=str(row["careers_page_url"]),
            ats_type=CareerAtsType(str(row["ats_type"])),
            ats_board_token=str(row["ats_board_token"]),
            poll_priority_tier=int(row["poll_priority_tier"]),
            is_global_seed=True,
            is_active=True,
        )
        return company

    existing.name = str(row["name"])
    existing.careers_page_url = str(row["careers_page_url"])
    existing.ats_type = CareerAtsType(str(row["ats_type"]))
    existing.ats_board_token = str(row["ats_board_token"])
    existing.poll_priority_tier = int(row["poll_priority_tier"])
    existing.is_global_seed = True
    existing.is_active = True
    return existing


async def load_seed_records(
    session: AsyncSession,
    records: list[dict[str, Any]],
    *,
    require_full_corpus: bool = True,
) -> LoadStats:
    """Upsert seed rows into ``watched_companies`` by slug (idempotent)."""
    validate_seed_records(records, require_full_corpus=require_full_corpus)

    inserted = 0
    updated = 0

    for row in records:
        slug = str(row["slug"])
        result = await session.execute(
            select(WatchedCompany).where(WatchedCompany.slug == slug)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(_row_to_company(row, existing=None))
            inserted += 1
        else:
            if not existing.is_global_seed:
                continue
            _row_to_company(row, existing=existing)
            updated += 1

    return LoadStats(inserted=inserted, updated=updated)


async def load_seed_file(session: AsyncSession, path: Path) -> LoadStats:
    """Load ``path`` and upsert into ``watched_companies``."""
    records = read_seed_json(path)
    return await load_seed_records(session, records)


__all__ = [
    "LoadStats",
    "REQUIRED_FIELDS",
    "TIER_TARGETS",
    "TOTAL_TARGET",
    "VALID_ATS_TYPES",
    "careers_page_url",
    "load_seed_file",
    "load_seed_records",
    "read_seed_json",
    "tier_counts",
    "validate_seed_records",
]
