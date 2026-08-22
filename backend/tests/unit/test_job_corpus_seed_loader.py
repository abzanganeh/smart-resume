"""Unit tests for TalioCV job corpus seed validation and loader logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.career_watch import CareerAtsType, WatchedCompany
from app.services.career_watch.job_corpus_seed import (
    MAX_CORPUS_SIZE,
    MIN_CORPUS_SIZE,
    TOTAL_TARGET,
    VALID_ATS_TYPES,
    careers_page_url,
    load_seed_records,
    read_seed_json,
    tier_counts,
    tier_targets_for_total,
    validate_seed_records,
)

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SEED_500_PATH = BACKEND_ROOT / "data" / "job_corpus" / "seed_500.json"
SEED_2000_PATH = BACKEND_ROOT / "data" / "job_corpus" / "seed_2000.json"


def _sample_rows(total: int = MIN_CORPUS_SIZE) -> list[dict[str, Any]]:
    targets = tier_targets_for_total(total)
    rows: list[dict[str, Any]] = []
    for tier, target in targets.items():
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
    assert len(rows) == total
    assert tier_counts(rows) == targets
    return rows


def test_tier_targets_for_total_scales_proportions() -> None:
    assert tier_targets_for_total(500) == {1: 100, 2: 175, 3: 225}
    assert tier_targets_for_total(2000) == {1: 400, 2: 700, 3: 900}
    assert sum(tier_targets_for_total(750).values()) == 750


def test_careers_page_url_supported_ats_types() -> None:
    assert careers_page_url("greenhouse", "stripe") == "https://boards.greenhouse.io/stripe"
    assert careers_page_url("lever", "spotify") == "https://jobs.lever.co/spotify"
    assert careers_page_url("ashby", "openai") == "https://jobs.ashbyhq.com/openai"
    assert (
        careers_page_url("smartrecruiters", "Acme")
        == "https://careers.smartrecruiters.com/Acme"
    )
    assert careers_page_url("workable", "acme") == "https://apply.workable.com/acme"
    assert careers_page_url("recruitee", "acme") == "https://acme.recruitee.com/"


def test_validate_seed_records_accepts_balanced_sample() -> None:
    validate_seed_records(_sample_rows(MIN_CORPUS_SIZE))


def test_validate_seed_records_accepts_two_thousand_row_sample() -> None:
    validate_seed_records(_sample_rows(TOTAL_TARGET))


def test_validate_seed_records_rejects_below_minimum() -> None:
    rows = _sample_rows(MIN_CORPUS_SIZE)[:-1]
    with pytest.raises(ValueError, match=str(MIN_CORPUS_SIZE)):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_above_maximum() -> None:
    rows = _sample_rows(MAX_CORPUS_SIZE)
    rows.append(
        {
            "name": "Overflow Co",
            "slug": "overflow-co",
            "ats_type": "greenhouse",
            "ats_board_token": "overflow",
            "poll_priority_tier": 3,
            "careers_page_url": careers_page_url("greenhouse", "overflow"),
        }
    )
    with pytest.raises(ValueError, match=str(MAX_CORPUS_SIZE)):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_duplicate_slugs() -> None:
    rows = _sample_rows(MIN_CORPUS_SIZE)
    rows[1]["slug"] = rows[0]["slug"]
    with pytest.raises(ValueError, match="duplicate slug"):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_invalid_ats_type() -> None:
    rows = _sample_rows(MIN_CORPUS_SIZE)
    rows[0]["ats_type"] = "workday"
    with pytest.raises(ValueError, match="invalid ats_type"):
        validate_seed_records(rows)


def test_validate_seed_records_rejects_tier_mismatch() -> None:
    rows = _sample_rows(MIN_CORPUS_SIZE)
    rows[0]["poll_priority_tier"] = 2
    with pytest.raises(ValueError, match="tier 1"):
        validate_seed_records(rows)


def test_tier_counts_helper() -> None:
    rows = _sample_rows(MIN_CORPUS_SIZE)
    assert tier_counts(rows) == tier_targets_for_total(MIN_CORPUS_SIZE)


@pytest.mark.asyncio
async def test_load_seed_records_inserts_and_updates() -> None:
    rows = _sample_rows(MIN_CORPUS_SIZE)[:3]
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
    rows = _sample_rows(MIN_CORPUS_SIZE)[:1]
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
    seed_path = SEED_2000_PATH if SEED_2000_PATH.is_file() else SEED_500_PATH
    if not seed_path.is_file():
        pytest.skip("job corpus seed JSON not generated yet")

    rows = read_seed_json(seed_path)
    validate_seed_records(rows)

    slugs = {row["slug"] for row in rows}
    assert MIN_CORPUS_SIZE <= len(slugs) <= MAX_CORPUS_SIZE
    assert tier_counts(rows) == tier_targets_for_total(len(rows))
    assert all(row["ats_type"] in VALID_ATS_TYPES for row in rows)

    stripe = next(row for row in rows if row["slug"] == "stripe")
    assert stripe["ats_type"] == "greenhouse"
    assert stripe["ats_board_token"] == "stripe"

    openai = next(row for row in rows if row["slug"] == "openai")
    assert openai["ats_type"] == "ashby"
    assert openai["ats_board_token"] == "openai"
