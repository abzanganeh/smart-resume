"""Unit tests for global daily poll budget (M19 slice 7)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.career_watch import CareerAtsType, WatchedCompany
from app.services.career_watch.poll_budget import apply_daily_poll_budget
from app.services.career_watch.poller import _due_companies_global_then_watchlist

pytestmark = pytest.mark.unit


def _company(
    slug: str,
    *,
    tier: int | None = 1,
    global_seed: bool = True,
) -> WatchedCompany:
    return WatchedCompany(
        id=uuid.uuid4(),
        name=slug,
        slug=slug,
        careers_page_url=f"https://example.com/{slug}",
        ats_type=CareerAtsType.greenhouse,
        ats_board_token=slug,
        poll_priority_tier=tier,
        is_global_seed=global_seed,
    )


def test_apply_daily_poll_budget_drops_tier3_first() -> None:
    tier1 = _company("tier1", tier=1)
    tier2 = _company("tier2", tier=2)
    tier3_a = _company("tier3a", tier=3)
    tier3_b = _company("tier3b", tier=3)
    watch = _company("watch", tier=3, global_seed=False)

    result = apply_daily_poll_budget(
        [tier3_a, tier1, tier3_b, tier2, watch],
        polls_today=97,
        budget=100,
    )
    slugs = {company.slug for company in result}
    assert slugs == {"tier1", "tier2", "watch"}


def test_apply_daily_poll_budget_no_trim_when_under_cap() -> None:
    companies = [_company("a", tier=3), _company("b", tier=3)]
    assert apply_daily_poll_budget(companies, polls_today=0, budget=100) == companies


@pytest.mark.asyncio
async def test_due_companies_applies_daily_budget() -> None:
    tier3 = _company("tier3", tier=3)
    tier1 = _company("tier1", tier=1)
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    session = AsyncMock()

    with (
        patch(
            "app.services.career_watch.poller.fetch_due_global_seeds",
            new=AsyncMock(return_value=[tier3, tier1]),
        ),
        patch(
            "app.services.career_watch.poller.fetch_due_companies",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.career_watch.poller.count_polls_today",
            new=AsyncMock(return_value=99),
        ),
        patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "GLOBAL_POLL_DAILY_BUDGET",
            100,
        ),
        patch(
            "app.services.career_watch.poller.apply_daily_poll_budget",
            wraps=apply_daily_poll_budget,
        ) as budget_fn,
    ):
        result = await _due_companies_global_then_watchlist(
            session, limit=10, now=now
        )

    budget_fn.assert_called_once()
    assert [company.slug for company in result] == ["tier1"]
