"""Integration tests for application tracker (Step 29)."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notification
from app.models.dashboard import ResumeRecord, ResumeRecordStatus
from app.models.tracker import ApplicationAttachment
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration

OVER_5MB = (5 * 1024 * 1024) + 1
SMALL_FILE = b"hello attachment"


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {**REGISTER_PAYLOAD, "email": f"tracker-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


async def _create_resume_record(
    db_session: AsyncSession,
    user_id: uuid.UUID,
) -> ResumeRecord:
    record = ResumeRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        session_id=f"sess-{uuid.uuid4().hex[:8]}",
        jd_title="Backend Engineer",
        jd_company="Acme Corp",
        jd_text_hash=uuid.uuid4().hex,
        tags=[],
        current_ats_score=80,
        starting_ats_score=75,
        status=ResumeRecordStatus.draft,
    )
    db_session.add(record)
    await db_session.flush()
    return record


async def _create_application(
    client: AsyncClient,
    token: str,
    *,
    resume_record_id: uuid.UUID | None = None,
) -> str:
    body: dict = {}
    if resume_record_id:
        body["resume_record_id"] = str(resume_record_id)
    else:
        body["jd_title"] = "Backend Engineer"
        body["jd_company"] = "Acme Corp"
    r = await client.post(
        "/api/applications",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
def _mock_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.tracker.s3.settings.AWS_S3_BUCKET_ATTACHMENTS",
        "test-attachments-bucket",
    )

    def _fake_upload(**kwargs) -> str:
        return f"attachments/{kwargs['user_id']}/{kwargs['application_id']}/fake.bin"

    def _fake_url(s3_key: str, *, filename: str, expires_in: int = 3600) -> str:
        return f"https://example.com/{s3_key}?name={filename}"

    monkeypatch.setattr("app.routers.tracker.upload_attachment", _fake_upload)
    monkeypatch.setattr("app.routers.tracker.generate_download_url", _fake_url)
    monkeypatch.setattr("app.routers.tracker.delete_attachment", lambda _key: None)


async def test_attachment_over_5mb_returns_413(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    record = await _create_resume_record(db_session, user_id)
    app_id = await _create_application(app_client, token, resume_record_id=record.id)

    files = {"file": ("large.bin", io.BytesIO(b"x" * OVER_5MB), "application/octet-stream")}
    r = await app_client.post(
        f"/api/applications/{app_id}/attachments",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 413


async def test_sixth_attachment_returns_422(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    record = await _create_resume_record(db_session, user_id)
    app_id = await _create_application(app_client, token, resume_record_id=record.id)

    for i in range(5):
        files = {"file": (f"file{i}.txt", io.BytesIO(SMALL_FILE), "text/plain")}
        r = await app_client.post(
            f"/api/applications/{app_id}/attachments",
            files=files,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.text

    files = {"file": ("file6.txt", io.BytesIO(SMALL_FILE), "text/plain")}
    r = await app_client.post(
        f"/api/applications/{app_id}/attachments",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422

    count = (
        await db_session.execute(
            select(ApplicationAttachment).where(
                ApplicationAttachment.application_id == uuid.UUID(app_id)
            )
        )
    ).scalars().all()
    assert len(count) == 5


async def test_status_offer_creates_congratulations_notification(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    record = await _create_resume_record(db_session, user_id)
    app_id = await _create_application(app_client, token, resume_record_id=record.id)

    r = await app_client.patch(
        f"/api/applications/{app_id}",
        json={"status": "offer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.type == "application_offer_congrats",
            )
        )
    ).scalars().all()
    assert len(rows) >= 1
    headlines = [row.title or (row.data or {}).get("headline", "") for row in rows]
    assert any("Congratulations" in headline for headline in headlines)


async def test_patch_status_applied_to_interviewing(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, _user_id = await _register(app_client)
    record = await _create_resume_record(db_session, _user_id)
    app_id = await _create_application(app_client, token, resume_record_id=record.id)

    await app_client.patch(
        f"/api/applications/{app_id}",
        json={"status": "applied"},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = await app_client.patch(
        f"/api/applications/{app_id}",
        json={"status": "interviewing"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "interviewing"
