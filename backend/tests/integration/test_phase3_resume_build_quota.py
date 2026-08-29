"""Regression: Phase 3 full rewrite debits resume_build quota (M18 slice 7)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import PhaseStatus
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.quota import QuotaAction
from app.services.session_store import create_session, update_session

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_phase3_run_debits_resume_build_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"phase3-quota-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Quota",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    await update_session(session)

    quota_mock = AsyncMock(return_value=None)

    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/3/run",
            json={"force": True},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.resume_build
