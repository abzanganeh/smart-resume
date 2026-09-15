"""Phase 4 stale refresh should not debit ats_recalc credits."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import ResumeRecord, ResumeRecordStatus, TailoringStage
from app.models.qa import QAOutput
from app.models.rewrite import TailoredResumeOutput
from app.models.session import PhaseStatus
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.exceptions import InsufficientCreditsError
from app.services.billing.quota import QuotaAction
from app.services.session_store import create_session, get_session, update_session

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_phase4_stale_refresh_skips_ats_recalc_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-stale-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Stale",
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
    session.phase3_status = PhaseStatus.done
    session.phase4_status = PhaseStatus.done
    session.phase4_output = QAOutput(
        checklist=[],
        overall_status="warn",
        user_action_required=[],
        ats_score=75,
        score_ceiling=96,
        blocking_issues=[],
    )
    session.phase4_stale_since = datetime.now(timezone.utc)
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
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )

    assert response.status_code == 202
    quota_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase4_force_rerun_after_score_debits_ats_recalc_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Force re-score without a stale marker must charge — not waive on prior output."""
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-force-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Force",
        tier=UserTier.free,
        credit_balance=1,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase4_status = PhaseStatus.done
    session.phase4_output = QAOutput(
        checklist=[],
        overall_status="warn",
        user_action_required=[],
        ats_score=75,
        score_ceiling=96,
        blocking_issues=[],
    )
    # No phase4_stale_since — user did not edit the resume after scoring.
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
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc


@pytest.mark.asyncio
async def test_phase4_second_force_after_stale_waived_rescore_debits_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After a waived stale re-score clears the marker, another force run must charge."""
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-double-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Double",
        tier=UserTier.free,
        credit_balance=2,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase4_status = PhaseStatus.done
    session.phase4_output = QAOutput(
        checklist=[],
        overall_status="warn",
        user_action_required=[],
        ats_score=75,
        score_ceiling=96,
        blocking_issues=[],
    )
    session.phase4_stale_since = datetime.now(timezone.utc)
    await update_session(session)

    quota_mock = AsyncMock(return_value=None)

    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        # First run: stale marker present → waived.
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )
        assert response.status_code == 202
        quota_mock.assert_not_awaited()

        # Simulate orchestrator clearing stale after successful Phase 4.
        refreshed = await get_session(session.session_id)
        assert refreshed is not None
        refreshed.phase4_stale_since = None
        await update_session(refreshed)

        # Second force without new edit → must charge.
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )
        assert response.status_code == 202
        quota_mock.assert_awaited_once()
        assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc


@pytest.mark.asyncio
async def test_phase4_rescore_debits_when_dashboard_record_has_prior_score(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Dashboard record score alone must not waive — only phase4_stale_since does."""
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-record-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Record",
        tier=UserTier.free,
        credit_balance=1,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase4_status = PhaseStatus.error
    await update_session(session)

    db_session.add(
        ResumeRecord(
            user_id=user.id,
            session_id=session.session_id,
            jd_title="Backend Engineer",
            jd_company="LedgerFlow Inc.",
            jd_text_hash="abc123",
            tags=[],
            current_ats_score=75,
            starting_ats_score=75,
            status=ResumeRecordStatus.draft,
            tailoring_stage=TailoringStage.polished,
        )
    )
    await db_session.commit()

    quota_mock = AsyncMock(return_value=None)

    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc


@pytest.mark.asyncio
async def test_phase4_force_rerun_with_output_and_dashboard_debits_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Production shape: scored session + dashboard row, no stale marker → must charge."""
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-prod-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Prod",
        tier=UserTier.free,
        credit_balance=1,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase4_status = PhaseStatus.done
    session.phase4_output = QAOutput(
        checklist=[],
        overall_status="warn",
        user_action_required=[],
        ats_score=75,
        score_ceiling=96,
        blocking_issues=[],
    )
    await update_session(session)

    db_session.add(
        ResumeRecord(
            user_id=user.id,
            session_id=session.session_id,
            jd_title="Backend Engineer",
            jd_company="LedgerFlow Inc.",
            jd_text_hash="abc123",
            tags=[],
            current_ats_score=75,
            starting_ats_score=75,
            status=ResumeRecordStatus.draft,
            tailoring_stage=TailoringStage.polished,
        )
    )
    await db_session.commit()

    quota_mock = AsyncMock(return_value=None)

    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc


@pytest.mark.asyncio
async def test_phase4_force_rerun_402_preserves_existing_score(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Billing failure must not reset_phase and wipe the visible Phase 4 score."""
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-402-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Preserve",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    prior_output = QAOutput(
        checklist=[],
        overall_status="warn",
        user_action_required=[],
        ats_score=75,
        score_ceiling=96,
        blocking_issues=[],
    )
    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase4_status = PhaseStatus.done
    session.phase4_output = prior_output
    await update_session(session)

    quota_mock = AsyncMock(
        side_effect=InsufficientCreditsError("ats_recalc", 0),
    )

    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )

    assert response.status_code == 402
    refreshed = await get_session(session.session_id)
    assert refreshed is not None
    assert refreshed.phase4_status == PhaseStatus.done
    assert refreshed.phase4_output is not None
    assert refreshed.phase4_output.ats_score == prior_output.ats_score


def _minimal_tailored() -> TailoredResumeOutput:
    return TailoredResumeOutput(
        contact={"name": "Jane Doe"},
        summary="Tailored summary",
        skills=["Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2020–2024",
                "bullets": ["Built APIs"],
                "removed_bullets": [],
                "keywords_injected": [],
            }
        ],
        projects=[],
        education=[],
        certifications=[],
        rewrite_notes=[],
        metrics_needed=[],
    )


@pytest.mark.asyncio
async def test_phase4_noop_tailored_patch_then_force_still_debits_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """No-op PATCH /tailored must not mint phase4_stale_since and waive billing."""
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-noop-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Noop",
        tier=UserTier.free,
        credit_balance=1,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    tailored = _minimal_tailored()
    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase3_output = tailored
    session.phase4_status = PhaseStatus.done
    session.phase4_output = QAOutput(
        checklist=[],
        overall_status="warn",
        user_action_required=[],
        ats_score=75,
        score_ceiling=96,
        blocking_issues=[],
    )
    await update_session(session)

    payload = tailored.model_dump()
    patch_response = await app_client.patch(
        f"/api/sessions/{session.session_id}/tailored",
        json={"tailored_output": payload},
    )
    assert patch_response.status_code == 200

    refreshed = await get_session(session.session_id)
    assert refreshed is not None
    assert refreshed.phase4_stale_since is None

    quota_mock = AsyncMock(return_value=None)
    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        response = await app_client.post(
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={"force": True},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc


@pytest.mark.asyncio
async def test_phase4_new_session_same_jd_after_rebind_debits_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Rebound dashboard row for a new session must not waive the first Phase 4 score."""
    from app.services.dashboard.resume_record import ensure_in_progress_resume_record

    user = User(
        id=uuid.uuid4(),
        email=f"phase4-rebind-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Rebind",
        tier=UserTier.free,
        credit_balance=1,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    jd_text = "Backend Engineer role at LedgerFlow Inc."
    old_session = await create_session()
    old_session.user_id = str(user.id)
    old_session.jd_raw = jd_text
    old_session.resume_raw = "Jane Doe"
    record = await ensure_in_progress_resume_record(
        db_session, user_id=user.id, session=old_session
    )
    assert record is not None
    record.current_ats_score = 75
    record.starting_ats_score = 75
    record.tailoring_stage = TailoringStage.polished
    await db_session.commit()

    new_session = await create_session()
    new_session.user_id = str(user.id)
    new_session.jd_raw = jd_text
    new_session.resume_raw = "Jane Doe"
    new_session.phase1_status = PhaseStatus.done
    new_session.phase2_status = PhaseStatus.done
    new_session.phase3_status = PhaseStatus.done
    await update_session(new_session)
    await ensure_in_progress_resume_record(
        db_session, user_id=user.id, session=new_session
    )
    await db_session.commit()

    quota_mock = AsyncMock(return_value=None)
    with patch(
        "app.routers.phases.check_and_increment_quota",
        quota_mock,
    ), patch(
        "app.routers.phases.should_skip_billing_quota",
        return_value=False,
    ):
        response = await app_client.post(
            f"/api/sessions/{new_session.session_id}/phases/4/run",
            json={},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc


@pytest.mark.asyncio
async def test_phase4_first_run_still_debits_ats_recalc_quota(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"phase4-first-{uuid.uuid4().hex[:8]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="First",
        tier=UserTier.free,
        credit_balance=1,
        accepted_tos_version="2026-06",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    session = await create_session()
    session.user_id = str(user.id)
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
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
            f"/api/sessions/{session.session_id}/phases/4/run",
            json={},
        )

    assert response.status_code == 202
    quota_mock.assert_awaited_once()
    assert quota_mock.await_args.kwargs["action"] == QuotaAction.ats_recalc
