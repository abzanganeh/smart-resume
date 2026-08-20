"""Integration tests for data export and account closure (Steps 33–34)."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import ResumeRecord, ResumeRecordStatus
from app.models.export import (
    CLOSURE_GRACE_DAYS,
    ClosureRequest,
    ExportJob,
    ExportJobStatus,
    EXPORT_PRESIGNED_TTL_SECONDS,
)
from app.models.master_resume import MasterResume
from app.models.notifications import Notification
from app.models.user import AuthProvider, User
from app.services.export.assembler import build_export_zip, process_export_job
from app.services.export.closure import cancel_closure, run_closure_tick, schedule_closure
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {**REGISTER_PAYLOAD, "email": f"export-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


def _mock_s3():
    uploaded: dict[str, bytes] = {}

    def fake_upload(*, Fileobj, Bucket, Key, ExtraArgs=None):  # noqa: N803
        uploaded[Key] = Fileobj.read()

    client = MagicMock()
    client.upload_fileobj.side_effect = fake_upload
    client.generate_presigned_url.return_value = "https://s3.example.com/export.zip?sig=test"
    client.delete_object.return_value = {}
    client.get_paginator.return_value.paginate.return_value = [{"Contents": []}]
    return client, uploaded


@pytest.fixture(autouse=True)
def _configure_export_env(monkeypatch):
    monkeypatch.setattr("app.config.settings.S3_EXPORT_BUCKET", "test-exports")
    monkeypatch.setattr("app.config.settings.INTERNAL_SCHEDULER_SECRET", "test-scheduler")
    monkeypatch.setattr("app.routers.account.settings.INTERNAL_SCHEDULER_SECRET", "test-scheduler")


async def test_export_zip_contains_required_files(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)

    db_session.add(
        MasterResume(
            id=uuid.uuid4(),
            user_id=user_id,
            raw_text="Jane Doe\nSoftware Engineer\nPython, FastAPI",
        )
    )
    db_session.add(
        ResumeRecord(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id="missing-session",
            jd_title="Backend Engineer",
            jd_company="Acme",
            jd_text_hash="abc123",
            status=ResumeRecordStatus.draft,
        )
    )
    await db_session.flush()

    fake_session = SimpleNamespace(phase3_output=object(), cover_letter_output=object())
    with patch("app.services.export.assembler.get_session", return_value=fake_session):
        with patch("app.services.export.assembler.render_pdf", return_value=b"resume-pdf"):
            with patch("app.services.export.assembler.render_docx", return_value=b"resume-docx"):
                with patch("app.services.export.assembler.render_txt", return_value="resume-txt"):
                    with patch(
                        "app.services.export.assembler.render_cover_letter_pdf",
                        return_value=b"cl-pdf",
                    ):
                        with patch(
                            "app.services.export.assembler.render_cover_letter_docx",
                            return_value=b"cl-docx",
                        ):
                            with patch(
                                "app.services.export.assembler.render_cover_letter_txt",
                                return_value="cl-txt",
                            ):
                                zip_bytes = await build_export_zip(db_session, user_id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "applications.csv" in names
        assert "interview_rounds.csv" in names
        assert "offers.csv" in names
        assert "ats_scores.csv" in names
        assert "saved_jobs.csv" in names
        assert "saved_searches.csv" in names
        assert "notifications_archive.csv" in names
        assert "account_info.json" in names
        assert "master_resume.txt" in names
        assert "master_resume.docx" in names
        assert "master_resume.pdf" in names
        assert "resumes/acme_backend_engineer/resume.pdf" in names
        assert "resumes/acme_backend_engineer/resume.docx" in names
        assert "resumes/acme_backend_engineer/resume.txt" in names
        assert "cover_letters/acme_backend_engineer/cover_letter.pdf" in names
        assert "cover_letters/acme_backend_engineer/cover_letter.docx" in names
        assert "cover_letters/acme_backend_engineer/cover_letter.txt" in names


async def test_export_presigned_url_valid_24h(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    job = ExportJob(id=uuid.uuid4(), user_id=user_id, status=ExportJobStatus.pending)
    db_session.add(job)
    await db_session.flush()

    mock_client, _ = _mock_s3()
    with patch("app.services.export.storage._s3_client", return_value=mock_client):
        with patch(
            "app.services.export.assembler.assemble_export_zip",
            return_value=b"PK\x03\x04fake",
        ):
            await process_export_job(db_session, job.id)

    await db_session.refresh(job)
    assert job.status == ExportJobStatus.ready
    assert job.presigned_url == "https://s3.example.com/export.zip?sig=test"
    assert job.presigned_url_expires_at is not None
    delta = job.presigned_url_expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=23, minutes=50) <= delta <= timedelta(hours=24, minutes=10)

    mock_client.generate_presigned_url.assert_called_once()
    _, kwargs = mock_client.generate_presigned_url.call_args
    assert kwargs.get("ExpiresIn") == EXPORT_PRESIGNED_TTL_SECONDS


async def test_create_export_api_returns_job_id(
    app_client: AsyncClient,
) -> None:
    token, _ = await _register(app_client)
    with patch("app.routers.account._run_export_background"):
        r = await app_client.post(
            "/api/account/export",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 202, r.text
    assert "job_id" in r.json()


async def test_run_closure_tick_hard_deletes_user_idempotent(
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"delete-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Delete Me",
        closure_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    db_session.add(user)
    await db_session.flush()

    scheduled = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(
        ClosureRequest(
            user_id=user.id,
            requested_at=datetime.now(timezone.utc) - timedelta(days=31),
            scheduled_delete_at=scheduled,
        )
    )
    await db_session.flush()

    with patch("app.services.export.closure.delete_attachment"):
        with patch("app.services.export.closure.delete_user_export_prefix"):
            with patch("app.services.export.storage.delete_export_object"):
                with patch(
                    "app.services.auth.email.send_account_deleted_email",
                    new=AsyncMock(return_value={"sent": False}),
                ):
                    result = await run_closure_tick(db_session, now=datetime.now(timezone.utc))
                    await db_session.flush()

    assert user.id in result.deleted
    gone = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one_or_none()
    assert gone is None

    result2 = await run_closure_tick(db_session, now=datetime.now(timezone.utc))
    assert result2.deleted == []


async def test_run_closure_tick_sends_day23_reminder(
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"remind-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Reminder User",
        closure_requested_at=datetime.now(timezone.utc) - timedelta(days=23),
    )
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    scheduled = now + timedelta(days=5)
    db_session.add(
        ClosureRequest(
            user_id=user.id,
            requested_at=now - timedelta(days=23),
            scheduled_delete_at=scheduled,
        )
    )
    await db_session.flush()

    result = await run_closure_tick(db_session, now=now)
    assert result.reminders_sent == 1
    assert result.deleted == []

    closure = (
        await db_session.execute(
            select(ClosureRequest).where(ClosureRequest.user_id == user.id)
        )
    ).scalar_one()
    assert closure.day23_reminder_sent_at is not None

    note = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.type == "account_closure_reminder",
            )
        )
    ).scalar_one()
    assert "7 days until account deletion" in note.title


async def test_cancel_closure_before_grace_restores_access(
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"cancel-{uuid.uuid4().hex[:6]}@example.com",
        auth_provider=AuthProvider.email,
        password_hash="x",
        display_name="Cancel Me",
    )
    db_session.add(user)
    await db_session.flush()

    with patch("app.services.billing.subscription.cancel_at_period_end", return_value={}):
        await schedule_closure(db_session, user=user)
    await db_session.refresh(user)
    assert user.closure_requested_at is not None

    ok = await cancel_closure(db_session, user=user)
    await db_session.flush()
    await db_session.refresh(user)

    assert ok is True
    assert user.closure_requested_at is None
    row = (
        await db_session.execute(
            select(ClosureRequest).where(ClosureRequest.user_id == user.id)
        )
    ).scalar_one()
    assert row.cancelled_at is not None


async def test_close_account_api(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    with patch("app.services.billing.subscription.cancel_at_period_end", return_value={}):
        r = await app_client.post(
            "/api/account/close",
            headers={"Authorization": f"Bearer {token}"},
            json={"cancel_subscription": True},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "scheduled_delete_at" in body

    user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    assert user.closure_requested_at is not None


async def test_scheduler_endpoint_requires_secret(app_client: AsyncClient) -> None:
    r = await app_client.delete("/api/account")
    assert r.status_code == 401

    r2 = await app_client.delete(
        "/api/account",
        headers={"X-Scheduler-Secret": "test-scheduler"},
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
