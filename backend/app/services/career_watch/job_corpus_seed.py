"""TalioCV job corpus seed validation and idempotent loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import CareerAtsType, WatchedCompany

VALID_ATS_TYPES: frozenset[str] = frozenset(
    {
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "workable",
        "recruitee",
        "breezy",
        "personio",
        "bamboohr",
    }
)
MIN_CORPUS_SIZE = 500
MAX_CORPUS_SIZE = 2000
TOTAL_TARGET = 2000
TIER1_RATIO = 0.20
TIER2_RATIO = 0.35
REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "slug",
    "ats_type",
    "ats_board_token",
    "poll_priority_tier",
    "careers_page_url",
)


def tier_targets_for_total(total: int) -> dict[int, int]:
    """Split ``total`` rows across poll tiers using the 20/35/45 corpus ratio."""
    if total < MIN_CORPUS_SIZE or total > MAX_CORPUS_SIZE:
        raise ValueError(
            f"corpus size must be between {MIN_CORPUS_SIZE} and {MAX_CORPUS_SIZE}, got {total}"
        )
    tier1 = round(total * TIER1_RATIO)
    tier2 = round(total * TIER2_RATIO)
    tier3 = total - tier1 - tier2
    return {1: tier1, 2: tier2, 3: tier3}


# Default tier targets for a full 2,000-company corpus.
TIER_TARGETS: dict[int, int] = tier_targets_for_total(TOTAL_TARGET)


def careers_page_url(ats_type: str, board_token: str) -> str:
    """Build the public careers board URL for a supported ATS."""
    token = board_token.strip()
    if ats_type == "greenhouse":
        return f"https://boards.greenhouse.io/{token}"
    if ats_type == "lever":
        return f"https://jobs.lever.co/{token}"
    if ats_type == "ashby":
        return f"https://jobs.ashbyhq.com/{token}"
    if ats_type == "smartrecruiters":
        return f"https://careers.smartrecruiters.com/{token}"
    if ats_type == "workable":
        return f"https://apply.workable.com/{token}"
    if ats_type == "recruitee":
        return f"https://{token}.recruitee.com/"
    if ats_type == "breezy":
        return f"https://{token}.breezy.hr/"
    if ats_type == "personio":
        return f"https://{token}.jobs.personio.com/"
    if ats_type == "bamboohr":
        return f"https://{token}.bamboohr.com/careers"
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
    total = len(records)
    if require_full_corpus and (total < MIN_CORPUS_SIZE or total > MAX_CORPUS_SIZE):
        raise ValueError(
            f"corpus size must be between {MIN_CORPUS_SIZE} and {MAX_CORPUS_SIZE}, got {total}"
        )
    if not require_full_corpus and not records:
        raise ValueError("seed records must not be empty")

    if require_full_corpus:
        expected = tier_targets_for_total(total)
        counts = tier_counts(records)
        for tier, target in expected.items():
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
        if tier not in (1, 2, 3):
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
    "MAX_CORPUS_SIZE",
    "MIN_CORPUS_SIZE",
    "REQUIRED_FIELDS",
    "TIER_TARGETS",
    "TOTAL_TARGET",
    "VALID_ATS_TYPES",
    "careers_page_url",
    "load_seed_file",
    "load_seed_records",
    "read_seed_json",
    "tier_counts",
    "tier_targets_for_total",
    "validate_seed_records",
]
