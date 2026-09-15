"""Unit tests for early dashboard resume record sync."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import ResumeRecord, ResumeRecordStatus, TailoringStage
from app.models.resume import ContactInfo, ParsedResume
from app.models.session import Session
from app.models.user import AuthProvider, User, UserTier
from app.services.dashboard.resume_record import (
    compute_jd_text_hash,
    compute_session_placeholder_hash,
    ensure_in_progress_resume_record,
    mark_resume_record_polished,
)
from app.services.session_store import create_session

pytestmark = pytest.mark.integration


async def _seed_user(db: AsyncSession, user_id: uuid.UUID | None = None) -> User:
    user = User(
        id=user_id or uuid.uuid4(),
        email=f"record-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Record User",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_ensure_in_progress_after_resume_upload(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    user_id = user.id
    session = await create_session()
    session.user_id = str(user_id)
    session.resume_raw = "Jane Doe\nSoftware Engineer"
    session.resume_parsed = ParsedResume(contact=ContactInfo(name="Jane Doe"))

    record = await ensure_in_progress_resume_record(
        db_session, user_id=user_id, session=session
    )
    await db_session.flush()

    assert record is not None
    assert record.tailoring_stage == TailoringStage.in_progress
    assert record.current_ats_score == 0
    assert record.jd_text_hash == compute_session_placeholder_hash(session.session_id)
    assert "Jane Doe" in record.jd_title


@pytest.mark.asyncio
async def test_mark_polished_updates_stage(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    user_id = user.id
    session = await create_session()
    session.user_id = str(user_id)
    session.resume_raw = "Resume text"

    await ensure_in_progress_resume_record(
        db_session, user_id=user_id, session=session
    )
    await db_session.flush()

    updated = await mark_resume_record_polished(
        db_session, user_id=user_id, session_id=session.session_id
    )
    assert updated is not None
    assert updated.tailoring_stage == TailoringStage.polished


@pytest.mark.asyncio
async def test_rebind_same_jd_resets_ats_score_for_new_session(
    db_session: AsyncSession,
) -> None:
    """Re-opening the same JD under a new session_id must not inherit prior ATS score."""
    user = await _seed_user(db_session)
    user_id = user.id
    jd_text = "Senior Backend Engineer at LedgerFlow Inc.\nPython, AWS"

    old_session = await create_session()
    old_session.user_id = str(user_id)
    old_session.jd_raw = jd_text
    old_session.resume_raw = "Jane Doe resume"

    first = await ensure_in_progress_resume_record(
        db_session, user_id=user_id, session=old_session
    )
    await db_session.flush()
    assert first is not None
    first.current_ats_score = 82
    first.starting_ats_score = 70
    first.tailoring_stage = TailoringStage.polished
    first.status = ResumeRecordStatus.draft
    first.session_cache = {"phase4_output": {"ats_score": 82}}
    await db_session.flush()

    new_session = await create_session()
    new_session.user_id = str(user_id)
    new_session.jd_raw = jd_text
    new_session.resume_raw = "Jane Doe resume"

    rebound = await ensure_in_progress_resume_record(
        db_session, user_id=user_id, session=new_session
    )
    await db_session.flush()

    assert rebound is not None
    assert rebound.session_id == new_session.session_id
    assert rebound.current_ats_score == 0
    assert rebound.starting_ats_score == 0
    assert rebound.tailoring_stage == TailoringStage.in_progress
    assert "phase4_output" not in (rebound.session_cache or {})
    assert rebound.jd_text_hash == compute_jd_text_hash(jd_text)
