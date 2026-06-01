"""Application tracker routes (IMPLEMENTATION_PLAN §6, SYSTEM_DESIGN §19.4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.limiter import limiter
from app.models.billing import Notification, NotificationStatus
from app.models.tracker import (
    Application,
    ApplicationAttachment,
    ApplicationStatus,
    InterviewFormat,
    InterviewOutcome,
    InterviewRound,
    OfferDecision,
    OfferDetail,
    RejectionReason,
)
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.tracker import (
    append_status_history,
    build_timeline,
    get_owned_application,
    list_applications,
    next_round_number,
    resolve_title_company,
    validate_attachment_upload,
)
from app.services.tracker.notifications import (
    create_custom_reminder,
    emit_status_change_notifications,
    schedule_follow_up_reminder,
)
from app.services.tracker.s3 import (
    delete_attachment,
    generate_download_url,
    upload_attachment,
)

router = APIRouter(tags=["tracker"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApplicationCreateRequest(BaseModel):
    resume_record_id: uuid.UUID | None = None
    jd_title: str | None = None
    jd_company: str | None = None
    status: ApplicationStatus = ApplicationStatus.draft
    applied_date: datetime | None = None
    follow_up_date: datetime | None = None
    notes: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    job_url: str | None = None


class ApplicationPatchRequest(BaseModel):
    status: ApplicationStatus | None = None
    applied_date: datetime | None = None
    follow_up_date: datetime | None = None
    notes: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    job_url: str | None = None
    rejection_reason: RejectionReason | None = None
    rejection_notes: str | None = None


class ApplicationSummary(BaseModel):
    id: uuid.UUID
    resume_record_id: uuid.UUID | None
    jd_title: str
    jd_company: str
    status: str
    applied_date: datetime | None
    follow_up_date: datetime | None
    created_at: datetime
    updated_at: datetime


class InterviewRoundCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    format: InterviewFormat
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=480)
    interviewers: list[str] = Field(default_factory=list)
    notes: str | None = None
    outcome: InterviewOutcome | None = None


class InterviewRoundPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    format: InterviewFormat | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=480)
    interviewers: list[str] | None = None
    notes: str | None = None
    outcome: InterviewOutcome | None = None


class OfferUpsertRequest(BaseModel):
    base_salary_usd: int | None = None
    bonus_usd: int | None = None
    equity_description: str | None = None
    sign_on_usd: int | None = None
    benefits: str | None = None
    location: str | None = None
    remote: bool = False
    start_date: date | None = None
    response_deadline: datetime | None = None
    decision: OfferDecision | None = None
    decision_notes: str | None = None


class ReminderCreateRequest(BaseModel):
    scheduled_at: datetime
    message: str = Field(..., min_length=1, max_length=500)


class ReminderResponse(BaseModel):
    id: uuid.UUID
    scheduled_at: datetime
    message: str
    status: str


class ApplicationDetailResponse(ApplicationSummary):
    notes: str | None
    contact_name: str | None
    contact_email: str | None
    job_url: str | None
    rejection_reason: str | None
    rejection_notes: str | None
    status_history: list[dict[str, Any]]
    interview_rounds: list[dict[str, Any]]
    offer_detail: dict[str, Any] | None
    attachments: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    attachment_usage: dict[str, int]


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _round_to_dict(rnd: InterviewRound) -> dict[str, Any]:
    return {
        "id": str(rnd.id),
        "round_number": rnd.round_number,
        "name": rnd.name,
        "format": rnd.format.value,
        "scheduled_at": rnd.scheduled_at.isoformat() if rnd.scheduled_at else None,
        "duration_minutes": rnd.duration_minutes,
        "interviewers": list(rnd.interviewers or []),
        "notes": rnd.notes,
        "outcome": rnd.outcome.value if rnd.outcome else None,
        "created_at": rnd.created_at.isoformat(),
    }


def _offer_to_dict(offer: OfferDetail | None) -> dict[str, Any] | None:
    if offer is None:
        return None
    return {
        "id": str(offer.id),
        "base_salary_usd": offer.base_salary_usd,
        "bonus_usd": offer.bonus_usd,
        "equity_description": offer.equity_description,
        "sign_on_usd": offer.sign_on_usd,
        "benefits": offer.benefits,
        "location": offer.location,
        "remote": offer.remote,
        "start_date": offer.start_date.isoformat() if offer.start_date else None,
        "response_deadline": (
            offer.response_deadline.isoformat() if offer.response_deadline else None
        ),
        "decision": offer.decision.value if offer.decision else None,
        "decision_notes": offer.decision_notes,
        "created_at": offer.created_at.isoformat(),
    }


def _attachment_to_dict(att: ApplicationAttachment, *, download_url: str | None = None) -> dict[str, Any]:
    payload = {
        "id": str(att.id),
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
        "uploaded_at": att.uploaded_at.isoformat(),
    }
    if download_url:
        payload["download_url"] = download_url
    return payload


def _summary(app: Application) -> ApplicationSummary:
    return ApplicationSummary(
        id=app.id,
        resume_record_id=app.resume_record_id,
        jd_title=app.jd_title,
        jd_company=app.jd_company,
        status=app.status.value,
        applied_date=app.applied_date,
        follow_up_date=app.follow_up_date,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def _detail(app: Application) -> ApplicationDetailResponse:
    total_bytes = sum(a.size_bytes for a in app.attachments)
    attachments = [_attachment_to_dict(a) for a in app.attachments]
    return ApplicationDetailResponse(
        **_summary(app).model_dump(),
        notes=app.notes,
        contact_name=app.contact_name,
        contact_email=app.contact_email,
        job_url=app.job_url,
        rejection_reason=app.rejection_reason.value if app.rejection_reason else None,
        rejection_notes=app.rejection_notes,
        status_history=list(app.status_history or []),
        interview_rounds=[_round_to_dict(r) for r in app.interview_rounds],
        offer_detail=_offer_to_dict(app.offer_detail),
        attachments=attachments,
        timeline=build_timeline(app),
        attachment_usage={
            "count": len(app.attachments),
            "total_bytes": total_bytes,
            "max_count": 5,
            "max_file_bytes": 5 * 1024 * 1024,
            "max_total_bytes": 25 * 1024 * 1024,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/api/applications", status_code=201)
@limiter.limit("30/minute")
async def create_application(
    request: Request,
    body: ApplicationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApplicationSummary:
    title, company, resume_id = await resolve_title_company(
        db,
        user.id,
        resume_record_id=body.resume_record_id,
        jd_title=body.jd_title,
        jd_company=body.jd_company,
    )
    now = _utcnow()
    app = Application(
        id=uuid.uuid4(),
        user_id=user.id,
        resume_record_id=resume_id,
        jd_title=title,
        jd_company=company,
        status=body.status,
        applied_date=body.applied_date,
        follow_up_date=body.follow_up_date,
        notes=body.notes,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        job_url=body.job_url,
        status_history=[],
        created_at=now,
        updated_at=now,
    )
    append_status_history(app, status=body.status, at=now)
    db.add(app)
    await db.flush()
    if body.follow_up_date:
        await schedule_follow_up_reminder(db, app=app, follow_up_date=body.follow_up_date)
    return _summary(app)


@router.get("/api/applications")
@limiter.limit("120/minute")
async def get_applications(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: ApplicationStatus | None = None,
    company: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[ApplicationSummary]:
    apps = await list_applications(
        db,
        user.id,
        status=status,
        company=company,
        date_from=date_from,
        date_to=date_to,
    )
    return [_summary(a) for a in apps]


@router.get("/api/applications/{application_id}")
@limiter.limit("120/minute")
async def get_application(
    request: Request,
    application_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApplicationDetailResponse:
    app = await get_owned_application(
        db, user.id, application_id, load_relations=True
    )
    return _detail(app)


@router.patch("/api/applications/{application_id}")
@limiter.limit("30/minute")
async def patch_application(
    request: Request,
    application_id: uuid.UUID,
    body: ApplicationPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApplicationSummary:
    app = await get_owned_application(db, user.id, application_id)
    old_status = app.status
    now = _utcnow()

    if body.status is not None and body.status != app.status:
        if body.status in {ApplicationStatus.rejected, ApplicationStatus.withdrawn}:
            reason = body.rejection_reason or app.rejection_reason
            if reason is None:
                raise HTTPException(
                    status_code=422,
                    detail="rejection_reason required when status is rejected or withdrawn",
                )
        app.status = body.status
        append_status_history(app, status=body.status, at=now)
        if body.status == ApplicationStatus.applied and app.applied_date is None:
            app.applied_date = now
        await emit_status_change_notifications(
            db, app=app, old_status=old_status, new_status=body.status
        )

    if body.applied_date is not None:
        app.applied_date = body.applied_date
    if body.follow_up_date is not None:
        app.follow_up_date = body.follow_up_date
        await schedule_follow_up_reminder(db, app=app, follow_up_date=body.follow_up_date)
    if body.notes is not None:
        app.notes = body.notes
    if body.contact_name is not None:
        app.contact_name = body.contact_name
    if body.contact_email is not None:
        app.contact_email = body.contact_email
    if body.job_url is not None:
        app.job_url = body.job_url
    if body.rejection_reason is not None:
        app.rejection_reason = body.rejection_reason
    if body.rejection_notes is not None:
        app.rejection_notes = body.rejection_notes

    app.updated_at = now
    await db.flush()
    return _summary(app)


@router.delete("/api/applications/{application_id}")
@limiter.limit("30/minute")
async def delete_application(
    request: Request,
    application_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    app = await get_owned_application(
        db, user.id, application_id, load_relations=True
    )
    for att in app.attachments:
        delete_attachment(att.s3_key)
    await db.delete(app)
    return {"ok": True}


@router.post("/api/applications/{application_id}/rounds", status_code=201)
@limiter.limit("30/minute")
async def add_interview_round(
    request: Request,
    application_id: uuid.UUID,
    body: InterviewRoundCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    app = await get_owned_application(db, user.id, application_id)
    rnd = InterviewRound(
        id=uuid.uuid4(),
        application_id=app.id,
        round_number=await next_round_number(db, app.id),
        name=body.name,
        format=body.format,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
        interviewers=body.interviewers,
        notes=body.notes,
        outcome=body.outcome,
    )
    db.add(rnd)
    if app.status == ApplicationStatus.applied:
        app.status = ApplicationStatus.interviewing
        append_status_history(app, status=ApplicationStatus.interviewing)
    app.updated_at = _utcnow()
    await db.flush()
    return _round_to_dict(rnd)


@router.patch("/api/applications/{application_id}/rounds/{round_id}")
@limiter.limit("30/minute")
async def patch_interview_round(
    request: Request,
    application_id: uuid.UUID,
    round_id: uuid.UUID,
    body: InterviewRoundPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    await get_owned_application(db, user.id, application_id)
    rnd = (
        await db.execute(
            select(InterviewRound).where(
                InterviewRound.id == round_id,
                InterviewRound.application_id == application_id,
            )
        )
    ).scalar_one_or_none()
    if rnd is None:
        raise HTTPException(status_code=404, detail="Interview round not found")

    if body.name is not None:
        rnd.name = body.name
    if body.format is not None:
        rnd.format = body.format
    if body.scheduled_at is not None:
        rnd.scheduled_at = body.scheduled_at
    if body.duration_minutes is not None:
        rnd.duration_minutes = body.duration_minutes
    if body.interviewers is not None:
        rnd.interviewers = body.interviewers
    if body.notes is not None:
        rnd.notes = body.notes
    if body.outcome is not None:
        rnd.outcome = body.outcome
    await db.flush()
    return _round_to_dict(rnd)


@router.delete("/api/applications/{application_id}/rounds/{round_id}")
@limiter.limit("30/minute")
async def delete_interview_round(
    request: Request,
    application_id: uuid.UUID,
    round_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    await get_owned_application(db, user.id, application_id)
    result = await db.execute(
        delete(InterviewRound).where(
            InterviewRound.id == round_id,
            InterviewRound.application_id == application_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Interview round not found")
    return {"ok": True}


@router.post("/api/applications/{application_id}/offer", status_code=201)
@limiter.limit("30/minute")
async def create_offer(
    request: Request,
    application_id: uuid.UUID,
    body: OfferUpsertRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    app = await get_owned_application(
        db, user.id, application_id, load_relations=True
    )
    if app.offer_detail is not None:
        raise HTTPException(status_code=409, detail="Offer details already exist")
    offer = OfferDetail(
        id=uuid.uuid4(),
        application_id=app.id,
        base_salary_usd=body.base_salary_usd,
        bonus_usd=body.bonus_usd,
        equity_description=body.equity_description,
        sign_on_usd=body.sign_on_usd,
        benefits=body.benefits,
        location=body.location,
        remote=body.remote,
        start_date=body.start_date,
        response_deadline=body.response_deadline,
        decision=body.decision,
        decision_notes=body.decision_notes,
    )
    db.add(offer)
    await db.flush()
    return _offer_to_dict(offer)


@router.patch("/api/applications/{application_id}/offer")
@limiter.limit("30/minute")
async def patch_offer(
    request: Request,
    application_id: uuid.UUID,
    body: OfferUpsertRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    app = await get_owned_application(
        db, user.id, application_id, load_relations=True
    )
    offer = app.offer_detail
    if offer is None:
        offer = OfferDetail(id=uuid.uuid4(), application_id=app.id)
        db.add(offer)

    if body.base_salary_usd is not None:
        offer.base_salary_usd = body.base_salary_usd
    if body.bonus_usd is not None:
        offer.bonus_usd = body.bonus_usd
    if body.equity_description is not None:
        offer.equity_description = body.equity_description
    if body.sign_on_usd is not None:
        offer.sign_on_usd = body.sign_on_usd
    if body.benefits is not None:
        offer.benefits = body.benefits
    if body.location is not None:
        offer.location = body.location
    offer.remote = body.remote
    if body.start_date is not None:
        offer.start_date = body.start_date
    if body.response_deadline is not None:
        offer.response_deadline = body.response_deadline
    if body.decision is not None:
        offer.decision = body.decision
    if body.decision_notes is not None:
        offer.decision_notes = body.decision_notes
    await db.flush()
    return _offer_to_dict(offer)


@router.post("/api/applications/{application_id}/attachments", status_code=201)
@limiter.limit("30/minute")
async def upload_application_attachment(
    request: Request,
    application_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    app = await get_owned_application(db, user.id, application_id)
    content = await file.read()
    size_bytes = len(content)
    await validate_attachment_upload(db, app.id, size_bytes)

    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "attachment"
    s3_key = upload_attachment(
        user_id=user.id,
        application_id=app.id,
        filename=filename,
        content_type=content_type,
        body=content,
        size_bytes=size_bytes,
    )
    att = ApplicationAttachment(
        id=uuid.uuid4(),
        application_id=app.id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        s3_key=s3_key,
    )
    db.add(att)
    try:
        await db.flush()
    except IntegrityError as exc:
        delete_attachment(s3_key)
        if "max_attachments_exceeded" in str(exc.orig):
            raise HTTPException(
                status_code=422,
                detail="Maximum 5 attachments per application",
            ) from exc
        raise
    app.updated_at = _utcnow()
    download_url = generate_download_url(s3_key, filename=filename)
    return _attachment_to_dict(att, download_url=download_url)


@router.delete("/api/applications/{application_id}/attachments/{attachment_id}")
@limiter.limit("30/minute")
async def delete_application_attachment(
    request: Request,
    application_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    await get_owned_application(db, user.id, application_id)
    att = (
        await db.execute(
            select(ApplicationAttachment).where(
                ApplicationAttachment.id == attachment_id,
                ApplicationAttachment.application_id == application_id,
            )
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    delete_attachment(att.s3_key)
    await db.delete(att)
    return {"ok": True}


@router.get("/api/applications/{application_id}/attachments/{attachment_id}/download")
@limiter.limit("60/minute")
async def download_application_attachment(
    request: Request,
    application_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    await get_owned_application(db, user.id, application_id)
    att = (
        await db.execute(
            select(ApplicationAttachment).where(
                ApplicationAttachment.id == attachment_id,
                ApplicationAttachment.application_id == application_id,
            )
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    url = generate_download_url(att.s3_key, filename=att.filename)
    return {"download_url": url}


@router.get("/api/applications/{application_id}/reminders")
@limiter.limit("120/minute")
async def list_reminders(
    request: Request,
    application_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[ReminderResponse]:
    await get_owned_application(db, user.id, application_id)
    rows = (
        await db.execute(
            select(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.type.in_(
                    ["application_custom_reminder", "application_follow_up"]
                ),
            )
            .order_by(desc(Notification.scheduled_at))
        )
    ).scalars().all()
    app_id = str(application_id)
    results: list[ReminderResponse] = []
    for row in rows:
        payload = row.payload or {}
        if payload.get("application_id") != app_id:
            continue
        results.append(
            ReminderResponse(
                id=row.id,
                scheduled_at=row.scheduled_at or row.created_at,
                message=payload.get("headline", ""),
                status=row.status.value,
            )
        )
    return results


@router.post("/api/applications/{application_id}/reminders", status_code=201)
@limiter.limit("30/minute")
async def create_reminder(
    request: Request,
    application_id: uuid.UUID,
    body: ReminderCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ReminderResponse:
    app = await get_owned_application(db, user.id, application_id)
    notification = await create_custom_reminder(
        db,
        app=app,
        scheduled_at=body.scheduled_at,
        message=body.message,
    )
    return ReminderResponse(
        id=notification.id,
        scheduled_at=notification.scheduled_at or body.scheduled_at,
        message=body.message,
        status=notification.status.value,
    )


@router.delete("/api/applications/{application_id}/reminders/{reminder_id}")
@limiter.limit("30/minute")
async def delete_reminder(
    request: Request,
    application_id: uuid.UUID,
    reminder_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    await get_owned_application(db, user.id, application_id)
    row = (
        await db.execute(
            select(Notification).where(
                Notification.id == reminder_id,
                Notification.user_id == user.id,
                Notification.type == "application_custom_reminder",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    payload = row.payload or {}
    if payload.get("application_id") != str(application_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    if row.status != NotificationStatus.pending:
        raise HTTPException(status_code=409, detail="Reminder already sent")
    await db.delete(row)
    return {"ok": True}
