"""Unit tests for poller global-first ordering (slice 4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.career_watch import CareerAtsType, WatchedCompany
from app.services.career_watch.poller import _due_companies_global_then_watchlist

pytestmark = pytest.mark.unit


def _company(slug: str) -> WatchedCompany:
    return WatchedCompany(
        id=uuid.uuid4(),
        name=slug,
        slug=slug,
        careers_page_url=f"https://example.com/{slug}",
        ats_type=CareerAtsType.greenhouse,
        ats_board_token=slug,
    )


@pytest.mark.asyncio
async def test_global_seeds_precede_watchlist_and_dedupe() -> None:
    global_co = _company("global")
    watch_co = _company("watch-only")
    overlap = _company("overlap")
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    session = AsyncMock()

    with (
        patch(
            "app.services.career_watch.poller.fetch_due_global_seeds",
            new=AsyncMock(return_value=[global_co, overlap]),
        ),
        patch(
            "app.services.career_watch.poller.fetch_due_companies",
            new=AsyncMock(return_value=[overlap, watch_co]),
        ),
        patch(
            "app.services.career_watch.poller.count_polls_today",
            new=AsyncMock(return_value=0),
        ),
    ):
        result = await _due_companies_global_then_watchlist(
            session, limit=10, now=now
        )

    assert [c.slug for c in result] == ["global", "overlap", "watch-only"]
