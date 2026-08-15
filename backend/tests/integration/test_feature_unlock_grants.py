"""Integration tests for runtime feature_unlock grant wiring."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.user import AuthProvider, User, UserTier
from app.services.admin.feature_unlocks import (
    active_feature_unlocks_for_user,
    user_has_feature_unlock,
)
from app.services.billing.quota import QuotaAction, check_and_increment_quota
from app.services.career_watch.limits import get_career_watch_limits

pytestmark = pytest.mark.integration


async def _seed_free_user(db_session: AsyncSession, *, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=email.split("@", 1)[0],
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _grant_feature(
    db_session: AsyncSession, *, user: User, feature: str
) -> None:
    db_session.add(
        AdminUserGrant(
            user_id=user.id,
            grant_type=AdminGrantType.feature_unlock,
            payload={"feature": feature},
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_active_feature_unlocks_for_user(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            AdminUserGrant(
                user_id=user_id,
                grant_type=AdminGrantType.feature_unlock,
                payload={"feature": "job_search"},
            ),
            AdminUserGrant(
                user_id=user_id,
                grant_type=AdminGrantType.feature_unlock,
                payload={"feature": "whisper"},
                revoked_at=now - timedelta(hours=1),
            ),
            AdminUserGrant(
                user_id=user_id,
                grant_type=AdminGrantType.feature_unlock,
                payload={"feature": "fit_analysis"},
                expires_at=now - timedelta(minutes=1),
            ),
            AdminUserGrant(
                user_id=user_id,
                grant_type=AdminGrantType.feature_unlock,
                payload={"feature": "unsupported"},
            ),
        ]
    )
    await db_session.commit()

    unlocked = await active_feature_unlocks_for_user(
        db_session, user_id=user_id, now=now
    )
    assert unlocked == {"job_search"}


@pytest.mark.asyncio
async def test_user_has_feature_unlock(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    db_session.add(
        AdminUserGrant(
            user_id=user_id,
            grant_type=AdminGrantType.feature_unlock,
            payload={"feature": "Career_Watch"},
        )
    )
    await db_session.commit()

    assert await user_has_feature_unlock(
        db_session, user_id=user_id, feature="career_watch"
    )
    assert not await user_has_feature_unlock(
        db_session, user_id=user_id, feature="whisper"
    )


@pytest.mark.asyncio
async def test_job_search_unlock_bypasses_subscription(db_session: AsyncSession) -> None:
    user = await _seed_free_user(db_session, email="job-unlock@example.com")
    await _grant_feature(db_session, user=user, feature="job_search")

    decision = await check_and_increment_quota(
        db_session, user=user, action=QuotaAction.job_search
    )
    assert decision.charged_to == "feature_unlock_job_search"


@pytest.mark.asyncio
async def test_fit_analysis_unlock_bypasses_subscription(
    db_session: AsyncSession,
) -> None:
    user = await _seed_free_user(db_session, email="fit-unlock@example.com")
    await _grant_feature(db_session, user=user, feature="fit_analysis")

    decision = await check_and_increment_quota(
        db_session, user=user, action=QuotaAction.fit_analysis
    )
    assert decision.charged_to == "feature_unlock_fit_analysis"


@pytest.mark.asyncio
async def test_career_watch_unlock_raises_free_limits(
    db_session: AsyncSession,
) -> None:
    user = await _seed_free_user(db_session, email="cw-unlock@example.com")
    await _grant_feature(db_session, user=user, feature="career_watch")

    max_companies, interval = await get_career_watch_limits(
        db_session, user=user
    )
    assert max_companies >= 10
    assert interval <= 15
