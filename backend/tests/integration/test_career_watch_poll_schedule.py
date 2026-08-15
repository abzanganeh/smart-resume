"""Integration tests for per-company Career Watch poll scheduling."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.career_watch import (
    CareerAtsType,
    UserWatchedCompany,
    WatchedCompany,
)
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.tier_limits import get_seed_rows
from app.services.career_watch.poll_schedule import (
    build_company_min_intervals,
    fetch_due_companies,
    load_interval_minutes_by_plan_code,
)

pytestmark = pytest.mark.integration


def _interval_map() -> dict[str, int]:
    return {row["plan_code"]: row["career_watch_interval_minutes"] for row in get_seed_rows()}


async def _make_user(db_session, suffix: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"cw-poll-{suffix}-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name=f"CW {suffix}",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_company(db_session, *, slug: str) -> WatchedCompany:
    company = WatchedCompany(
        id=uuid.uuid4(),
        name=f"Company {slug}",
        slug=slug,
        careers_page_url=f"https://boards.greenhouse.io/{slug}",
        ats_type=CareerAtsType.greenhouse,
        ats_board_token=slug,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest.mark.asyncio
async def test_company_interval_is_min_across_watchers(db_session) -> None:
    company = await _make_company(db_session, slug="acme")
    free_user = await _make_user(db_session, "free")
    premium_user = await _make_user(db_session, "premium")
    db_session.add(
        AdminUserGrant(
            user_id=premium_user.id,
            grant_type=AdminGrantType.tier_override,
            payload={"plan_code": "monthly_premium"},
        )
    )
    for user in (free_user, premium_user):
        db_session.add(
            UserWatchedCompany(
                id=uuid.uuid4(),
                user_id=user.id,
                watched_company_id=company.id,
                keywords=["engineer"],
                is_active=True,
            )
        )
    await db_session.flush()

    intervals = await build_company_min_intervals(db_session)
    expected = _interval_map()["monthly_premium"]
    assert intervals[company.id] == expected


@pytest.mark.asyncio
async def test_fetch_due_companies_respects_premium_interval(db_session) -> None:
    now = datetime.now(timezone.utc)
    company = await _make_company(db_session, slug="beta")
    company.last_polled_at = now - timedelta(minutes=10)
    premium_user = await _make_user(db_session, "prem-only")
    db_session.add(
        AdminUserGrant(
            user_id=premium_user.id,
            grant_type=AdminGrantType.tier_override,
            payload={"plan_code": "monthly_plus"},
        )
    )
    db_session.add(
        UserWatchedCompany(
            id=uuid.uuid4(),
            user_id=premium_user.id,
            watched_company_id=company.id,
            keywords=["backend"],
            is_active=True,
        )
    )
    await db_session.flush()

    due = await fetch_due_companies(db_session, limit=10, now=now)
    due_ids = {row.id for row in due}
    assert company.id in due_ids


@pytest.mark.asyncio
async def test_fetch_due_companies_skips_free_tier_before_interval(db_session) -> None:
    now = datetime.now(timezone.utc)
    company = await _make_company(db_session, slug="gamma")
    company.last_polled_at = now - timedelta(minutes=10)
    free_user = await _make_user(db_session, "free-only")
    db_session.add(
        UserWatchedCompany(
            id=uuid.uuid4(),
            user_id=free_user.id,
            watched_company_id=company.id,
            keywords=["data"],
            is_active=True,
        )
    )
    await db_session.flush()

    due = await fetch_due_companies(db_session, limit=10, now=now)
    assert company.id not in {row.id for row in due}


@pytest.mark.asyncio
async def test_load_interval_minutes_includes_seed_defaults(db_session) -> None:
    intervals = await load_interval_minutes_by_plan_code(db_session)
    assert intervals["monthly_plus"] == 5
    assert intervals["free"] == 30
