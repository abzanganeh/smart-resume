"""Integration tests for POST /api/resumes/bulk (RP4 Step 28)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import ResumeRecord, ResumeRecordStatus
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {**REGISTER_PAYLOAD, "email": f"bulk-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


async def _seed_records(
    db_session: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[ResumeRecord, ResumeRecord]:
    now = datetime.now(timezone.utc)
    first = ResumeRecord(
        user_id=user_id,
        session_id="sess-bulk-1",
        jd_title="Backend Engineer",
        jd_company="Acme",
        jd_text_hash="hash-bulk-1",
        tags=["python"],
        current_ats_score=80,
        starting_ats_score=75,
        status=ResumeRecordStatus.draft,
        created_at=now,
        updated_at=now,
    )
    second = ResumeRecord(
        user_id=user_id,
        session_id="sess-bulk-2",
        jd_title="Platform Engineer",
        jd_company="Beta",
        jd_text_hash="hash-bulk-2",
        tags=[],
        current_ats_score=72,
        starting_ats_score=70,
        status=ResumeRecordStatus.applied,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([first, second])
    await db_session.flush()
    return first, second


@pytest.mark.asyncio
async def test_bulk_delete_soft_deletes_selected_records(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    first, second = await _seed_records(db_session, user_id)
    headers = {"Authorization": f"Bearer {token}"}

    res = await app_client.post(
        "/api/resumes/bulk",
        json={"action": "delete", "ids": [str(first.id), str(second.id)]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == 2

    listed = await app_client.get("/api/resumes", headers=headers)
    assert listed.json()["total"] == 0

    rows = (
        await db_session.execute(
            select(ResumeRecord).where(ResumeRecord.user_id == user_id)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert all(r.deleted_at is not None for r in rows)


@pytest.mark.asyncio
async def test_bulk_tag_merges_tags_on_selected_records(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    first, second = await _seed_records(db_session, user_id)
    headers = {"Authorization": f"Bearer {token}"}

    res = await app_client.post(
        "/api/resumes/bulk",
        json={
            "action": "tag",
            "ids": [str(first.id), str(second.id)],
            "tags": ["remote", "python"],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["tagged"] == 2

    await db_session.refresh(first)
    await db_session.refresh(second)
    assert "remote" in first.tags
    assert "python" in first.tags
    assert "remote" in second.tags


@pytest.mark.asyncio
async def test_bulk_export_returns_download_manifest(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    first, second = await _seed_records(db_session, user_id)
    headers = {"Authorization": f"Bearer {token}"}

    res = await app_client.post(
        "/api/resumes/bulk",
        json={"action": "export", "ids": [str(first.id), str(second.id)]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert len(body["exports"]) == 2
    urls = {item["download_url"] for item in body["exports"]}
    assert f"/api/resumes/{first.id}/download?format=zip" in urls
    assert f"/api/resumes/{second.id}/download?format=zip" in urls


@pytest.mark.asyncio
async def test_bulk_tag_requires_tags(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    first, _second = await _seed_records(db_session, user_id)
    headers = {"Authorization": f"Bearer {token}"}

    res = await app_client.post(
        "/api/resumes/bulk",
        json={"action": "tag", "ids": [str(first.id)], "tags": []},
        headers=headers,
    )
    assert res.status_code == 422
