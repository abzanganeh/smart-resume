"""Unit tests for TalioCV job corpus seed validation and loader logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.career_watch import CareerAtsType, WatchedCompany
from app.services.career_watch.job_corpus_seed import (
    TIER_TARGETS,
    TOTAL_TARGET,
    VALID_ATS_TYPES,
    careers_page_url,
    load_seed_records,
    read_seed_json,
    tier_counts,
    validate_seed_records,
)

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = BACKEND_ROOT / "data" / "job_corpus" / "seed_500.json"


def _sample_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counts = {1: 0, 2: 0, 3: 0}
    for tier, target in TIER_TARGETS.items():
        for index in range(target):
            slug = f"tier{tier}-company-{index}"
            token = f"board-{tier}-{index}"
            rows.append(
                {
                    "name": f"Tier {tier} Company {index}",
                    "slug": slug,
                    "ats_type": "greenhouse",
                    "ats_board_token": token,
                    "poll_priority_tier": tier,
                    "careers_page_url": careers_page_url("greenhouse", token),
                }
            )
            counts[tier] += 1
    assert len(rows) == TOTAL_TARGET
    assert counts == TIER_TARGETS
    return rows


def test_careers_page_url_supported_ats_types() -> None:
    assert careers_page_url("greenhouse", "stripe") == "https://boards.greenhouse.io/stripe"
    assert careers_page_url("lever", "spotify") == "https://jobs.lever.co/spotify"
    assert careers_page_url("ashby", "openai") == "https://jobs.ashbyhq.com/openai"


def test_validate_seed_records_accepts_balanced_sample() -> None:
    validate_seed_records(_sample_rows())


def test_validate_seed_records_rejects_wrong_count() -> None:
    rows = _sample_rows()[:-1]
    with pytest.raises(ValueError, match="expected 500"):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_duplicate_slugs() -> None:
    rows = _sample_rows()
    rows[1]["slug"] = rows[0]["slug"]
    with pytest.raises(ValueError, match="duplicate slug"):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_invalid_ats_type() -> None:
    rows = _sample_rows()
    rows[0]["ats_type"] = "workday"
    with pytest.raises(ValueError, match="invalid ats_type"):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_tier_mismatch() -> None:
    rows = _sample_rows()
    rows[0]["poll_priority_tier"] = 2
    with pytest.raises(ValueError, match="tier 1"):
        validate_seed_records(rows)


def test_tier_counts_helper() -> None:
    rows = _sample_rows()
    assert tier_counts(rows) == TIER_TARGETS


@pytest.mark.asyncio
async def test_load_seed_records_inserts_and_updates() -> None:
    rows = _sample_rows()[:3]
    existing = WatchedCompany(
        name="Old",
        slug=rows[0]["slug"],
        careers_page_url="https://example.com",
        ats_type=CareerAtsType.unknown,
        is_global_seed=False,
    )

    session = MagicMock()
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=existing)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
    session.execute = AsyncMock(side_effect=results)
    session.add = MagicMock()

    stats = await load_seed_records(session, rows, require_full_corpus=False)

    assert stats.inserted == 2
    assert stats.updated == 0
    assert existing.is_global_seed is False
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_load_seed_records_updates_existing_global_seed() -> None:
    rows = _sample_rows()[:1]
    existing = WatchedCompany(
        name="Old",
        slug=rows[0]["slug"],
        careers_page_url="https://example.com",
        ats_type=CareerAtsType.unknown,
        is_global_seed=True,
    )

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
    )
    session.add = MagicMock()

    stats = await load_seed_records(session, rows, require_full_corpus=False)

    assert stats.inserted == 0
    assert stats.updated == 1
    assert existing.ats_type == CareerAtsType.greenhouse


def test_seed_file_on_disk_when_present() -> None:
    if not SEED_PATH.is_file():
        pytest.skip("seed_500.json not generated yet")

    rows = read_seed_json(SEED_PATH)
    validate_seed_records(rows)

    slugs = {row["slug"] for row in rows}
    assert len(slugs) == TOTAL_TARGET
    assert tier_counts(rows) == TIER_TARGETS
    assert all(row["ats_type"] in VALID_ATS_TYPES for row in rows)

    stripe = next(row for row in rows if row["slug"] == "stripe")
    assert stripe["ats_type"] == "greenhouse"
    assert stripe["ats_board_token"] == "stripe"

    openai = next(row for row in rows if row["slug"] == "openai")
    assert openai["ats_type"] == "ashby"
    assert openai["ats_board_token"] == "openai"
