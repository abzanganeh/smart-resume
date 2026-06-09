"""Dashboard and resume record routes (IMPLEMENTATION_PLAN §6, SYSTEM_DESIGN §19.3)."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.limiter import limiter
from app.models.billing import CreditKind, Subscription, SubscriptionStatus
from app.models.dashboard import (
    AtsScoreHistory,
    ResumeRecord,
    ResumeRecordStatus,
)
from app.models.master_resume import MasterResume
from app.models.tracker import Application
from app.models.jobs import SavedJob
from app.models.session import PhaseStatus
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.billing.credits import get_balance
from app.services.billing.quota import (
    PLAN_RESUMES_PER_PERIOD,
    PLAN_SEARCHES_PER_PERIOD,
)
from app.services.dashboard.activity import build_recent_activity
from app.services.export_service import render_docx, render_pdf, render_txt
from app.services.session_store import create_session, get_session, update_session

router = APIRouter(tags=["dashboard"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActivityItem(BaseModel):
    type: str
    at: str
    title: str
    subtitle: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class DashboardSummaryResponse(BaseModel):
    display_name: str
    tier: str
    credit_balance: int
    next_billing_date: str | None
    subscription: dict[str, Any] | None
    counts: dict[str, int]
    recent_activity: list[ActivityItem]
    ats_trend: list[dict[str, Any]]


class ResumeListItem(BaseModel):
    id: uuid.UUID
    session_id: str
    display_name: str | None
    jd_title: str
    jd_company: str
    tags: list[str]
    current_ats_score: int
    starting_ats_score: int
    ats_score_delta: int
    status: str
    tailoring_stage: str
    created_at: datetime
    updated_at: datetime


class ResumeListResponse(BaseModel):
    items: list[ResumeListItem]
    total: int
    page: int
    page_size: int


class ResumeDetailResponse(ResumeListItem):
    jd_text_hash: str
    score_history: list[dict[str, Any]]
    linked_application_id: uuid.UUID | None = None


class ResumePatchRequest(BaseModel):
    tags: list[str] | None = None
    status: ResumeRecordStatus | None = None
    display_name: str | None = None


class BulkActionRequest(BaseModel):
    action: Literal["delete", "tag", "export"]
    ids: list[uuid.UUID] = Field(..., min_length=1)
    tags: list[str] | None = None


class DuplicateResponse(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    record_id: uuid.UUID,
) -> ResumeRecord:
    record = (
        await db.execute(
            select(ResumeRecord).where(
                ResumeRecord.id == record_id,
                ResumeRecord.user_id == user_id,
                ResumeRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Resume record not found")
    return record


def _record_to_list_item(record: ResumeRecord) -> ResumeListItem:
    return ResumeListItem(
        id=record.id,
        session_id=record.session_id,
        display_name=record.display_name,
        jd_title=record.jd_title,
        jd_company=record.jd_company,
        tags=list(record.tags or []),
        current_ats_score=record.current_ats_score,
        starting_ats_score=record.starting_ats_score,
        ats_score_delta=record.ats_score_delta,
        status=record.status.value,
        tailoring_stage=record.tailoring_stage.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _ats_trend_last_30_days(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta

    cutoff = cutoff - timedelta(days=30)
    rows = (
        await db.execute(
            select(AtsScoreHistory, ResumeRecord)
            .join(ResumeRecord, AtsScoreHistory.resume_record_id == ResumeRecord.id)
            .where(
                ResumeRecord.user_id == user_id,
                ResumeRecord.deleted_at.is_(None),
                AtsScoreHistory.triggered_at >= cutoff,
            )
            .order_by(AtsScoreHistory.triggered_at)
        )
    ).all()
    return [
        {
            "date": history.triggered_at.date().isoformat(),
            "score": history.score,
            "resume_id": str(record.id),
            "jd_title": record.jd_title,
            "jd_company": record.jd_company,
        }
        for history, record in rows
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/summary")
@limiter.limit("120/minute")
async def dashboard_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummaryResponse:
    sub = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status != SubscriptionStatus.expired,
            )
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    resume_count = (
        await db.execute(
            select(func.count())
            .select_from(ResumeRecord)
            .where(
                ResumeRecord.user_id == user.id,
                ResumeRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    saved_jobs_count = (
        await db.execute(
            select(func.count())
            .select_from(SavedJob)
            .where(SavedJob.user_id == user.id)
        )
    ).scalar_one()

    application_count = (
        await db.execute(
            select(func.count())
            .select_from(Application)
            .where(Application.user_id == user.id)
        )
    ).scalar_one()

    master_row = (
        await db.execute(
            select(MasterResume.chunk_count).where(MasterResume.user_id == user.id)
        )
    ).scalar_one_or_none()
    master_chunk_count = int(master_row or 0)

    free_credits = await get_balance(db, user_id=user.id, credit_kind=CreditKind.free)

    subscription_payload: dict[str, Any] | None = None
    next_billing: str | None = None
    tier = "free"

    if sub is not None:
        tier = sub.plan.value
        resumes_limit = PLAN_RESUMES_PER_PERIOD.get(sub.plan, 0)
        searches_limit = PLAN_SEARCHES_PER_PERIOD.get(sub.plan, 0)
        next_billing = sub.period_end.isoformat()
        subscription_payload = {
            "id": str(sub.id),
            "plan": sub.plan.value,
            "billing_cycle": sub.billing_cycle.value,
            "status": sub.status.value,
            "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
            "period_start": sub.period_start.isoformat(),
            "period_end": sub.period_end.isoformat(),
            "resumes_used": sub.resumes_used,
            "resumes_limit": resumes_limit,
            "searches_used": sub.searches_used,
            "searches_limit": searches_limit,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "paused_at": sub.paused_at.isoformat() if sub.paused_at else None,
        }

    activity = await build_recent_activity(db, user.id, limit=10)

    return DashboardSummaryResponse(
        display_name=user.display_name,
        tier=tier,
        credit_balance=free_credits,
        next_billing_date=next_billing,
        subscription=subscription_payload,
        counts={
            "resumes": resume_count,
            "master_chunks": master_chunk_count,
            "applications": application_count,
            "saved_jobs": saved_jobs_count,
        },
        recent_activity=[ActivityItem(**item) for item in activity],
        ats_trend=await _ats_trend_last_30_days(db, user.id),
    )


@router.get("/api/resumes")
@limiter.limit("120/minute")
async def list_resumes(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    q: str | None = None,
    statuses: list[ResumeRecordStatus] = Query(default_factory=list, alias="status"),
    tag: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ats_min: int | None = Query(default=None, ge=0, le=100),
    ats_max: int | None = Query(default=None, ge=0, le=100),
    sort: Literal["date", "ats_score", "company"] = "date",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ResumeListResponse:
    query = select(ResumeRecord).where(
        ResumeRecord.user_id == user.id,
        ResumeRecord.deleted_at.is_(None),
    )

    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(
            or_(
                func.lower(ResumeRecord.jd_title).like(pattern),
                func.lower(ResumeRecord.jd_company).like(pattern),
                func.lower(func.coalesce(ResumeRecord.display_name, "")).like(pattern),
                ResumeRecord.tags.astext.ilike(pattern),
            )
        )
    if statuses:
        query = query.where(ResumeRecord.status.in_(statuses))
    if tag:
        query = query.where(ResumeRecord.tags.contains([tag]))
    if date_from is not None:
        query = query.where(ResumeRecord.created_at >= date_from)
    if date_to is not None:
        query = query.where(ResumeRecord.created_at <= date_to)
    if ats_min is not None:
        query = query.where(ResumeRecord.current_ats_score >= ats_min)
    if ats_max is not None:
        query = query.where(ResumeRecord.current_ats_score <= ats_max)

    sort_map = {
        "date": desc(ResumeRecord.updated_at),
        "ats_score": desc(ResumeRecord.current_ats_score),
        "company": ResumeRecord.jd_company.asc(),
    }
    query = query.order_by(sort_map[sort])

    count_query = select(func.count()).select_from(ResumeRecord).where(
        ResumeRecord.user_id == user.id,
        ResumeRecord.deleted_at.is_(None),
    )
    if q:
        pattern = f"%{q.lower()}%"
        count_query = count_query.where(
            or_(
                func.lower(ResumeRecord.jd_title).like(pattern),
                func.lower(ResumeRecord.jd_company).like(pattern),
                func.lower(func.coalesce(ResumeRecord.display_name, "")).like(pattern),
                ResumeRecord.tags.astext.ilike(pattern),
            )
        )
    if statuses:
        count_query = count_query.where(ResumeRecord.status.in_(statuses))
    if tag:
        count_query = count_query.where(ResumeRecord.tags.contains([tag]))
    if date_from is not None:
        count_query = count_query.where(ResumeRecord.created_at >= date_from)
    if date_to is not None:
        count_query = count_query.where(ResumeRecord.created_at <= date_to)
    if ats_min is not None:
        count_query = count_query.where(ResumeRecord.current_ats_score >= ats_min)
    if ats_max is not None:
        count_query = count_query.where(ResumeRecord.current_ats_score <= ats_max)

    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    rows = (
        await db.execute(query.offset(offset).limit(page_size))
    ).scalars().all()

    return ResumeListResponse(
        items=[_record_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/resumes/{record_id}")
@limiter.limit("120/minute")
async def get_resume(
    request: Request,
    record_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ResumeDetailResponse:
    record = await _get_owned_record(db, user.id, record_id)
    history = (
        await db.execute(
            select(AtsScoreHistory)
            .where(AtsScoreHistory.resume_record_id == record.id)
            .order_by(AtsScoreHistory.triggered_at)
        )
    ).scalars().all()
    linked = (
        await db.execute(
            select(Application.id).where(Application.resume_record_id == record.id)
        )
    ).scalar_one_or_none()
    base = _record_to_list_item(record)
    return ResumeDetailResponse(
        **base.model_dump(),
        jd_text_hash=record.jd_text_hash,
        score_history=[
            {
                "id": str(h.id),
                "score": h.score,
                "recalc_type": h.recalc_type.value,
                "triggered_at": h.triggered_at.isoformat(),
            }
            for h in history
        ],
        linked_application_id=linked,
    )


@router.patch("/api/resumes/{record_id}")
@limiter.limit("30/minute")
async def patch_resume(
    request: Request,
    record_id: uuid.UUID,
    body: ResumePatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ResumeListItem:
    record = await _get_owned_record(db, user.id, record_id)
    if body.tags is not None:
        record.tags = body.tags
    if body.status is not None:
        record.status = body.status
    if body.display_name is not None:
        cleaned = body.display_name.strip()
        record.display_name = cleaned or None
    record.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _record_to_list_item(record)


@router.delete("/api/resumes/{record_id}")
@limiter.limit("30/minute")
async def delete_resume(
    request: Request,
    record_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    record = await _get_owned_record(db, user.id, record_id)
    record.deleted_at = datetime.now(timezone.utc)
    return {"ok": True}


@router.post("/api/resumes/{record_id}/duplicate", status_code=201)
@limiter.limit("20/minute")
async def duplicate_resume(
    request: Request,
    record_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> DuplicateResponse:
    record = await _get_owned_record(db, user.id, record_id)
    source = await get_session(record.session_id)
    if source is None:
        raise HTTPException(
            status_code=410,
            detail="Original session expired — duplicate unavailable",
        )

    new_session = await create_session(
        provider=source.provider,
        model=source.model,
    )
    new_session.user_id = str(user.id)
    new_session.jd_raw = source.jd_raw
    # Keep duplication deterministic: only prefill reusable inputs and JD text.
    # Phase outputs are intentionally not copied to avoid stale-state forks.
    new_session.user_info = source.user_info
    new_session.resume_raw = source.resume_raw
    new_session.resume_parsed = source.resume_parsed
    new_session.phase1_status = PhaseStatus.pending
    new_session.phase2_status = PhaseStatus.pending
    new_session.phase3_status = PhaseStatus.pending
    new_session.phase4_status = PhaseStatus.pending
    await update_session(new_session)
    return DuplicateResponse(session_id=new_session.session_id)


@router.get("/api/resumes/{record_id}/download")
@limiter.limit("60/minute")
async def download_resume(
    request: Request,
    record_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    format: Literal["pdf", "docx", "txt", "zip"] = "pdf",
) -> StreamingResponse:
    record = await _get_owned_record(db, user.id, record_id)
    session = await get_session(record.session_id)
    if session is None or session.phase3_output is None:
        raise HTTPException(status_code=422, detail="No tailored resume available to export")

    slug = record.jd_company.replace(" ", "_")[:40]

    if format == "zip":
        pdf_bytes = await render_pdf(session)
        docx_bytes = render_docx(session)
        txt_bytes = render_txt(session).encode()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{slug}_resume.pdf", pdf_bytes)
            zf.writestr(f"{slug}_resume.docx", docx_bytes)
            zf.writestr(f"{slug}_resume.txt", txt_bytes)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.read()]),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{slug}_resume.zip"'
            },
        )

    if format == "pdf":
        content = await render_pdf(session)
        media_type = "application/pdf"
        filename = f"{slug}_resume.pdf"
    elif format == "docx":
        content = render_docx(session)
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        filename = f"{slug}_resume.docx"
    else:
        content = render_txt(session).encode()
        media_type = "text/plain"
        filename = f"{slug}_resume.txt"

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/resumes/{record_id}/scores")
@limiter.limit("120/minute")
async def resume_scores(
    request: Request,
    record_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    record = await _get_owned_record(db, user.id, record_id)
    rows = (
        await db.execute(
            select(AtsScoreHistory)
            .where(AtsScoreHistory.resume_record_id == record.id)
            .order_by(AtsScoreHistory.triggered_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "score": r.score,
            "recalc_type": r.recalc_type.value,
            "triggered_at": r.triggered_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/api/resumes/bulk")
@limiter.limit("10/minute")
async def bulk_resume_action(
    request: Request,
    body: BulkActionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    records = (
        await db.execute(
            select(ResumeRecord).where(
                ResumeRecord.user_id == user.id,
                ResumeRecord.id.in_(body.ids),
                ResumeRecord.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    if not records:
        raise HTTPException(status_code=404, detail="No matching resume records")

    now = datetime.now(timezone.utc)

    if body.action == "delete":
        for record in records:
            record.deleted_at = now
        return {"ok": True, "deleted": len(records)}

    if body.action == "tag":
        if not body.tags:
            raise HTTPException(status_code=422, detail="tags required for tag action")
        for record in records:
            merged = list(dict.fromkeys([*(record.tags or []), *body.tags]))
            record.tags = merged
            record.updated_at = now
        return {"ok": True, "tagged": len(records)}

    # export — return manifest of download URLs (client fetches individually)
    return {
        "ok": True,
        "exports": [
            {
                "id": str(r.id),
                "title": r.jd_title,
                "company": r.jd_company,
                "download_url": f"/api/resumes/{r.id}/download?format=zip",
            }
            for r in records
        ],
    }
