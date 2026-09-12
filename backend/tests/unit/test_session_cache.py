"""Session cache persistence + Redis restore for polished resumes."""

from __future__ import annotations

import uuid

import pytest

from app.models.rewrite import TailoredResumeOutput
from app.models.session import PhaseStatus, Session
from app.services.dashboard.session_cache import (
    build_session_cache,
    persist_session_cache,
    restore_session_from_record,
)
from app.services.session_store import get_session, update_session
from app.models.dashboard import ResumeRecord, TailoringStage, ResumeRecordStatus
from app.services.dashboard.resume_record import compute_jd_text_hash


pytestmark = pytest.mark.unit


def _tailored() -> TailoredResumeOutput:
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
async def test_build_session_cache_requires_tailored_output() -> None:
    assert build_session_cache(Session(session_id="s1")) is None
    session = Session(session_id="s1", phase3_output=_tailored())
    cache = build_session_cache(session)
    assert cache is not None
    assert cache["tailored_output"]["summary"] == "Tailored summary"


@pytest.mark.asyncio
async def test_restore_session_from_record_rehydrates_redis(db_session) -> None:
    user_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    tailored = _tailored()
    session = Session(
        session_id=session_id,
        user_id=str(user_id),
        jd_raw="Senior Engineer at Example Corp",
        resume_raw="Jane Doe resume",
        phase3_output=tailored,
        phase3_status=PhaseStatus.done,
    )
    record = ResumeRecord(
        user_id=user_id,
        session_id=session_id,
        jd_title="Senior Engineer",
        jd_company="Example Corp",
        jd_text_hash=compute_jd_text_hash(session.jd_raw or ""),
        tailoring_stage=TailoringStage.polished,
        status=ResumeRecordStatus.draft,
        session_cache=build_session_cache(session),
    )
    db_session.add(record)
    await db_session.commit()

    restored = await restore_session_from_record(
        db_session,
        session_id=session_id,
        user_id=user_id,
    )
    assert restored is not None
    assert restored.phase3_output is not None
    assert restored.phase3_output.summary == "Tailored summary"
    assert restored.phase3_status == PhaseStatus.done

    loaded = await get_session(session_id)
    assert loaded is not None
    assert loaded.phase3_output is not None


@pytest.mark.asyncio
async def test_persist_session_cache_updates_record(db_session) -> None:
    user_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    record = ResumeRecord(
        user_id=user_id,
        session_id=session_id,
        jd_title="Role",
        jd_company="Co",
        jd_text_hash=compute_jd_text_hash("jd"),
        tailoring_stage=TailoringStage.polished,
        status=ResumeRecordStatus.draft,
    )
    db_session.add(record)
    await db_session.commit()

    session = Session(
        session_id=session_id,
        user_id=str(user_id),
        jd_raw="jd",
        phase3_output=_tailored(),
        phase3_status=PhaseStatus.done,
    )
    await persist_session_cache(
        db_session,
        user_id=user_id,
        session_id=session_id,
        session=session,
    )
    await db_session.commit()
    await db_session.refresh(record)
    assert record.session_cache is not None
    assert record.session_cache["tailored_output"]["summary"] == "Tailored summary"
