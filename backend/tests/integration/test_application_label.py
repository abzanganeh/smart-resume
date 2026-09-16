"""Application label on tailoring sessions."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import ResumeRecord, ResumeRecordStatus, TailoringStage
from app.models.resume import ContactInfo, ParsedResume
from app.models.user import AuthProvider, User, UserTier
from app.services.dashboard.resume_record import ensure_in_progress_resume_record
from app.services.session_store import create_session, get_session, update_session

pytestmark = pytest.mark.integration


async def _seed_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"label-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Label User",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def test_patch_application_label_persists_on_session(
    app_client: AsyncClient,
) -> None:
    created = await app_client.post("/api/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    r = await app_client.patch(
        f"/api/sessions/{session_id}/application",
        json={"display_name": "Acme Health — Senior Backend"},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Acme Health — Senior Backend"

    stored = await get_session(session_id)
    assert stored is not None
    assert stored.application_display_name == "Acme Health — Senior Backend"

    check = await app_client.get(f"/api/sessions/{session_id}")
    assert check.status_code == 200
    assert check.json()["application_display_name"] == "Acme Health — Senior Backend"


async def test_patch_application_label_syncs_resume_record_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    session = await create_session()
    session.user_id = str(user.id)
    session.resume_raw = "Ali Barzin\nSoftware Engineer"
    session.resume_parsed = ParsedResume(contact=ContactInfo(name="Ali Barzin"))
    await update_session(session)
    await ensure_in_progress_resume_record(db_session, user_id=user.id, session=session)
    await db_session.commit()

    r = await app_client.patch(
        f"/api/sessions/{session.session_id}/application",
        json={"display_name": "Acme Health — Senior Backend"},
    )
    assert r.status_code == 200, r.text

    record = (
        await db_session.execute(
            select(ResumeRecord).where(
                ResumeRecord.user_id == user.id,
                ResumeRecord.session_id == session.session_id,
            )
        )
    ).scalar_one()
    assert record.display_name == "Acme Health — Senior Backend"
    assert record.jd_title == "Senior Backend"
    assert record.jd_company == "Acme Health"


@pytest.mark.asyncio
async def test_application_label_replaces_resume_upload_placeholder_metadata(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    session = await create_session()
    session.user_id = str(user.id)
    session.application_display_name = "Acme Health — Senior Backend"
    session.resume_raw = "Ali Barzin\nSoftware Engineer"
    session.resume_parsed = ParsedResume(contact=ContactInfo(name="Ali Barzin"))

    record = await ensure_in_progress_resume_record(
        db_session, user_id=user.id, session=session
    )
    await db_session.flush()

    assert record is not None
    assert record.display_name == "Acme Health — Senior Backend"
    assert record.jd_title == "Senior Backend"
    assert record.jd_company == "Acme Health"


@pytest.mark.asyncio
async def test_tracker_uses_resume_record_display_name_over_placeholder_title(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register_for_tracker(app_client)
    record = ResumeRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        session_id=f"sess-{uuid.uuid4().hex[:8]}",
        jd_title="Ali Barzin — resume draft",
        jd_company="—",
        jd_text_hash=uuid.uuid4().hex,
        display_name="Acme Health — Senior Backend",
        tags=[],
        current_ats_score=80,
        starting_ats_score=75,
        status=ResumeRecordStatus.draft,
        tailoring_stage=TailoringStage.polished,
    )
    db_session.add(record)
    await db_session.commit()

    r = await app_client.post(
        "/api/applications",
        json={"resume_record_id": str(record.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["jd_title"] == "Senior Backend"
    assert body["jd_company"] == "Acme Health"


@pytest.mark.asyncio
async def test_tracker_rejects_second_application_for_same_resume_record(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register_for_tracker(app_client)
    record = ResumeRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        session_id=f"sess-{uuid.uuid4().hex[:8]}",
        jd_title="Ali Barzin — resume draft",
        jd_company="—",
        jd_text_hash=uuid.uuid4().hex,
        display_name="Acme Health — Senior Backend",
        tags=[],
        current_ats_score=80,
        starting_ats_score=75,
        status=ResumeRecordStatus.draft,
        tailoring_stage=TailoringStage.polished,
    )
    db_session.add(record)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    first = await app_client.post(
        "/api/applications",
        json={"resume_record_id": str(record.id)},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await app_client.post(
        "/api/applications",
        json={"resume_record_id": str(record.id)},
        headers=headers,
    )
    assert second.status_code == 409, second.text
    assert "already linked" in second.text.lower()


async def _register_for_tracker(client: AsyncClient) -> tuple[str, uuid.UUID]:
    from tests.integration.test_auth import REGISTER_PAYLOAD

    payload = {
        **REGISTER_PAYLOAD,
        "email": f"label-tracker-{uuid.uuid4().hex[:8]}@example.com",
    }
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])
