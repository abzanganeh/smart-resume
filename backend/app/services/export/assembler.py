"""Assemble a GDPR-style ZIP export for a user account."""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any

import structlog
from docx import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dashboard import AtsScoreHistory, ResumeRecord
from app.models.export import ExportJob, ExportJobStatus, EXPORT_PRESIGNED_TTL_SECONDS
from app.models.jobs import JobCache, SavedJob, SavedSearch
from app.models.master_resume import MasterResume
from app.models.notifications import Notification, NotificationPreference
from app.models.tracker import Application
from app.models.user import AuthAuditLog, User
from app.services.export.storage import generate_export_download_url, upload_export_zip
from app.services.export_service import (
    render_cover_letter_docx,
    render_cover_letter_pdf,
    render_cover_letter_txt,
    render_docx,
    render_pdf,
    render_txt,
)
from app.services.notifications.factory import build_notification
from app.models.notifications import NotificationChannel
from app.services.session_store import get_session

log = structlog.get_logger("export.assembler")


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", text.strip().lower())
    return (cleaned[:60] or "item").strip("_")


def _master_resume_txt(raw: str) -> str:
    return raw.strip()


def _master_resume_docx(raw: str) -> bytes:
    doc = Document()
    for line in raw.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


async def _master_resume_pdf(raw: str) -> bytes:
    from weasyprint import CSS, HTML

    escaped = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = f"<pre style='white-space:pre-wrap;font-family:Georgia,serif'>{escaped}</pre>"
    css = CSS(string="@page { size: Letter; margin: 0.75in; }")
    return HTML(string=html).write_pdf(stylesheets=[css])


def _write_csv(zf: zipfile.ZipFile, name: str, headers: list[str], rows: list[list[Any]]) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    zf.writestr(name, buf.getvalue())


async def build_export_zip(session: AsyncSession, user_id: uuid.UUID) -> bytes:
    """Collect all user data per §19.6 manifest into an in-memory ZIP."""
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise ValueError("user not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Resumes + cover letters from resume records / sessions
        records = (
            await session.execute(
                select(ResumeRecord).where(
                    ResumeRecord.user_id == user_id,
                    ResumeRecord.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        for record in records:
            slug = _slug(f"{record.jd_company}_{record.jd_title}")
            sess = await get_session(record.session_id)
            if sess is None:
                continue
            if sess.phase3_output is not None:
                pdf_bytes = await render_pdf(sess)
                docx_bytes = render_docx(sess)
                txt_bytes = render_txt(sess).encode()
                zf.writestr(f"resumes/{slug}/resume.pdf", pdf_bytes)
                zf.writestr(f"resumes/{slug}/resume.docx", docx_bytes)
                zf.writestr(f"resumes/{slug}/resume.txt", txt_bytes)
            if sess.cover_letter_output is not None:
                cl_pdf = await render_cover_letter_pdf(sess)
                cl_docx = render_cover_letter_docx(sess)
                cl_txt = render_cover_letter_txt(sess).encode()
                zf.writestr(f"cover_letters/{slug}/cover_letter.pdf", cl_pdf)
                zf.writestr(f"cover_letters/{slug}/cover_letter.docx", cl_docx)
                zf.writestr(f"cover_letters/{slug}/cover_letter.txt", cl_txt)

        # Applications CSV
        apps = (
            await session.execute(
                select(Application)
                .where(Application.user_id == user_id)
                .options(
                    selectinload(Application.interview_rounds),
                    selectinload(Application.offer_detail),
                )
            )
        ).scalars().all()

        _write_csv(
            zf,
            "applications.csv",
            [
                "id",
                "jd_title",
                "jd_company",
                "status",
                "applied_date",
                "follow_up_date",
                "contact_name",
                "contact_email",
                "job_url",
                "rejection_reason",
                "notes",
                "created_at",
            ],
            [
                [
                    str(a.id),
                    a.jd_title,
                    a.jd_company,
                    a.status.value,
                    a.applied_date.isoformat() if a.applied_date else "",
                    a.follow_up_date.isoformat() if a.follow_up_date else "",
                    a.contact_name or "",
                    a.contact_email or "",
                    a.job_url or "",
                    a.rejection_reason.value if a.rejection_reason else "",
                    (a.notes or "").replace("\n", " "),
                    a.created_at.isoformat(),
                ]
                for a in apps
            ],
        )

        interview_rows: list[list[Any]] = []
        offer_rows: list[list[Any]] = []
        for app in apps:
            for rnd in app.interview_rounds:
                interview_rows.append(
                    [
                        str(rnd.id),
                        str(app.id),
                        rnd.round_number,
                        rnd.name,
                        rnd.format.value,
                        rnd.scheduled_at.isoformat() if rnd.scheduled_at else "",
                        rnd.duration_minutes or "",
                        ";".join(rnd.interviewers or []),
                        rnd.outcome.value if rnd.outcome else "",
                        (rnd.notes or "").replace("\n", " "),
                    ]
                )
            if app.offer_detail:
                od = app.offer_detail
                offer_rows.append(
                    [
                        str(od.id),
                        str(app.id),
                        od.base_salary_usd or "",
                        od.bonus_usd or "",
                        od.equity_description or "",
                        od.sign_on_usd or "",
                        od.location or "",
                        od.remote,
                        od.start_date.isoformat() if od.start_date else "",
                        od.response_deadline.isoformat() if od.response_deadline else "",
                        od.decision.value if od.decision else "",
                    ]
                )

        _write_csv(
            zf,
            "interview_rounds.csv",
            [
                "id",
                "application_id",
                "round_number",
                "name",
                "format",
                "scheduled_at",
                "duration_minutes",
                "interviewers",
                "outcome",
                "notes",
            ],
            interview_rows,
        )
        _write_csv(
            zf,
            "offers.csv",
            [
                "id",
                "application_id",
                "base_salary_usd",
                "bonus_usd",
                "equity_description",
                "sign_on_usd",
                "location",
                "remote",
                "start_date",
                "response_deadline",
                "decision",
            ],
            offer_rows,
        )

        # ATS scores
        ats_rows: list[list[Any]] = []
        for record in records:
            history = (
                await session.execute(
                    select(AtsScoreHistory).where(
                        AtsScoreHistory.resume_record_id == record.id
                    )
                )
            ).scalars().all()
            for h in history:
                ats_rows.append(
                    [
                        str(h.id),
                        str(record.id),
                        record.jd_title,
                        record.jd_company,
                        h.score,
                        h.recalc_type.value,
                        h.triggered_at.isoformat(),
                    ]
                )
        _write_csv(
            zf,
            "ats_scores.csv",
            [
                "id",
                "resume_record_id",
                "jd_title",
                "jd_company",
                "score",
                "recalc_type",
                "triggered_at",
            ],
            ats_rows,
        )

        # Saved jobs
        saved_jobs = (
            await session.execute(
                select(SavedJob, JobCache)
                .join(JobCache, SavedJob.job_cache_id == JobCache.id)
                .where(SavedJob.user_id == user_id)
            )
        ).all()
        _write_csv(
            zf,
            "saved_jobs.csv",
            ["saved_job_id", "title", "company", "location", "apply_url", "saved_at"],
            [
                [
                    str(sj.id),
                    jc.title,
                    jc.company,
                    jc.location,
                    jc.apply_url,
                    sj.created_at.isoformat(),
                ]
                for sj, jc in saved_jobs
            ],
        )

        saved_searches = (
            await session.execute(
                select(SavedSearch).where(SavedSearch.user_id == user_id)
            )
        ).scalars().all()
        _write_csv(
            zf,
            "saved_searches.csv",
            ["id", "name", "query", "location", "alert_frequency", "created_at"],
            [
                [
                    str(s.id),
                    s.name,
                    s.query,
                    s.location or "",
                    s.alert_frequency.value,
                    s.created_at.isoformat(),
                ]
                for s in saved_searches
            ],
        )

        # Master resume
        master = (
            await session.execute(
                select(MasterResume).where(MasterResume.user_id == user_id)
            )
        ).scalar_one_or_none()
        if master and master.raw_text.strip():
            zf.writestr("master_resume.txt", _master_resume_txt(master.raw_text))
            zf.writestr("master_resume.docx", _master_resume_docx(master.raw_text))
            zf.writestr("master_resume.pdf", await _master_resume_pdf(master.raw_text))

        # Notifications archive
        notifications = (
            await session.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at)
            )
        ).scalars().all()
        _write_csv(
            zf,
            "notifications_archive.csv",
            ["id", "type", "category", "title", "body", "created_at", "read_at"],
            [
                [
                    str(n.id),
                    n.type,
                    n.category,
                    n.title,
                    (n.body or "").replace("\n", " "),
                    n.created_at.isoformat(),
                    n.read_at.isoformat() if n.read_at else "",
                ]
                for n in notifications
            ],
        )

        # Account info
        prefs = (
            await session.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        audit_summary = (
            await session.execute(
                select(AuthAuditLog.event, AuthAuditLog.created_at)
                .where(AuthAuditLog.user_id == user_id)
                .order_by(AuthAuditLog.created_at.desc())
                .limit(50)
            )
        ).all()
        account_info = {
            "email": user.email,
            "display_name": user.display_name,
            "tier": user.tier.value,
            "auth_provider": user.auth_provider.value,
            "created_at": user.created_at.isoformat(),
            "email_verified_at": (
                user.email_verified_at.isoformat() if user.email_verified_at else None
            ),
            "marketing_opt_in": user.marketing_opt_in,
            "notification_preferences": {
                "email_enabled_categories": (
                    list(prefs.email_enabled_categories) if prefs else []
                ),
                "in_app_enabled_categories": (
                    list(prefs.in_app_enabled_categories) if prefs else []
                ),
                "web_push_enabled": prefs.web_push_enabled if prefs else False,
                "sms_enabled": prefs.sms_enabled if prefs else False,
                "digest_mode": prefs.digest_mode.value if prefs else "off",
            },
            "auth_audit_summary": [
                {"event": row.event.value, "at": row.created_at.isoformat()}
                for row in audit_summary
            ],
        }
        zf.writestr(
            "account_info.json",
            json.dumps(account_info, indent=2, sort_keys=True),
        )

    buf.seek(0)
    return buf.read()


async def process_export_job(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Build ZIP, upload to S3, update job row, notify user."""
    job = (
        await session.execute(select(ExportJob).where(ExportJob.id == job_id))
    ).scalar_one_or_none()
    if job is None:
        return

    job.status = ExportJobStatus.processing
    await session.flush()

    try:
        zip_bytes = await build_export_zip(session, job.user_id)
        s3_key = upload_export_zip(
            user_id=job.user_id,
            job_id=job.id,
            body=zip_bytes,
        )
        presigned = generate_export_download_url(s3_key)
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        job.s3_key = s3_key
        job.presigned_url = presigned
        job.presigned_url_expires_at = now + timedelta(
            seconds=EXPORT_PRESIGNED_TTL_SECONDS
        )
        job.status = ExportJobStatus.ready
        job.completed_at = now
        job.error = None

        session.add(
            build_notification(
                user_id=job.user_id,
                type="export_ready",
                channel=NotificationChannel.multi,
                category="data_export",
                title="Your data export is ready",
                body="Download your ZIP within 24 hours.",
                data={
                    "export_job_id": str(job.id),
                    "download_url": presigned,
                    "url": "/settings/danger",
                },
            )
        )
        await session.flush()
        log.info("export.job.completed", job_id=str(job.id), user_id=str(job.user_id))
    except Exception as exc:
        job.status = ExportJobStatus.failed
        job.error = str(exc)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        await session.flush()
        log.error(
            "export.job.failed",
            job_id=str(job.id),
            user_id=str(job.user_id),
            error=str(exc),
        )


assemble_export_zip = build_export_zip

__all__ = ["assemble_export_zip", "build_export_zip", "process_export_job"]
