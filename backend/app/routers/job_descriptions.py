"""Extension job description endpoints (Strategy B Phase 2).

``POST /api/job-descriptions`` saves a JD captured by the browser extension
and immediately mints a Flint handoff token so the user can open it in Flint.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.models.job_description import JobDescription
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.autofill import (
    RECENT_TAILORED_LIMIT,
    build_autofill_fields,
    detect_platform,
    extract_contact,
    url_host,
)
from app.services.flint_handoff import create_jd_handoff_token
from app.services.session_store import get_session
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["job-descriptions"])


class SaveJDRequest(BaseModel):
    url: str = Field(default="", max_length=2048)
    title: str = Field(default="", max_length=512)
    company: str = Field(default="", max_length=512)
    text: str = Field(..., min_length=1)
    source: str = Field(default="extension", max_length=64)


class SaveJDResponse(BaseModel):
    jd_id: str
    export_token: str
    expires_in: int


class JobDescriptionResponse(BaseModel):
    id: str
    url: str | None
    title: str | None
    company: str | None
    text: str
    source: str
    created_at: str
    session_id: str | None = None


class AutofillFieldPayload(BaseModel):
    key: str
    selector: str
    value: str
    label: str | None = None


class AutofillPayloadResponse(BaseModel):
    jd_id: str
    platform: str
    fields: list[AutofillFieldPayload]


class RecentTailoredSessionItem(BaseModel):
    jd_id: str
    title: str
    company: str
    url_host: str
    tailored_at: str


class RecentTailoredSessionsResponse(BaseModel):
    sessions: list[RecentTailoredSessionItem]


@router.get(
    "/api/job-descriptions/recent-tailored",
    response_model=RecentTailoredSessionsResponse,
)
@limiter.limit("60/minute")
async def list_recent_tailored_sessions(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecentTailoredSessionsResponse:
    """Recent extension JDs with a completed tailored resume for autofill matching."""
    rows = (
        await db.execute(
            select(JobDescription)
            .where(
                JobDescription.user_id == user.id,
                JobDescription.session_id.isnot(None),
            )
            .order_by(JobDescription.created_at.desc())
            .limit(RECENT_TAILORED_LIMIT * 3)
        )
    ).scalars().all()

    sessions: list[RecentTailoredSessionItem] = []
    for row in rows:
        if not row.session_id:
            continue
        session = await get_session(row.session_id)
        if session is None or session.phase3_output is None:
            continue
        sessions.append(
            RecentTailoredSessionItem(
                jd_id=str(row.id),
                title=row.title or "",
                company=row.company or "",
                url_host=url_host(row.url),
                tailored_at=row.created_at.isoformat(),
            )
        )
        if len(sessions) >= RECENT_TAILORED_LIMIT:
            break

    return RecentTailoredSessionsResponse(sessions=sessions)


@router.get(
    "/api/job-descriptions/{jd_id}/autofill-payload",
    response_model=AutofillPayloadResponse,
)
@limiter.limit("60/minute")
async def get_autofill_payload(
    request: Request,
    jd_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutofillPayloadResponse:
    """Return mapped autofill field values for a tailored extension JD."""
    try:
        jd_uuid = uuid.UUID(jd_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc

    row = (
        await db.execute(
            select(JobDescription).where(
                JobDescription.id == jd_uuid,
                JobDescription.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if not row.session_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "resume_not_tailored_yet"},
        )

    session = await get_session(row.session_id)
    if session is None or session.phase3_output is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "resume_not_tailored_yet"},
        )

    platform = detect_platform(row.url)
    contact = extract_contact(session)
    fields = build_autofill_fields(contact, platform)

    return AutofillPayloadResponse(
        jd_id=str(row.id),
        platform=platform,
        fields=[AutofillFieldPayload(**field) for field in fields],
    )


@router.get("/api/job-descriptions/{jd_id}", response_model=JobDescriptionResponse)
@limiter.limit("60/minute")
async def get_job_description(
    request: Request,
    jd_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobDescriptionResponse:
    """Load an extension-saved JD for the tailoring wizard (TalioCV web)."""
    try:
        jd_uuid = uuid.UUID(jd_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc

    row = (
        await db.execute(
            select(JobDescription).where(
                JobDescription.id == jd_uuid,
                JobDescription.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return JobDescriptionResponse(
        id=str(row.id),
        url=row.url,
        title=row.title,
        company=row.company,
        text=row.text,
        source=row.source,
        created_at=row.created_at.isoformat(),
        session_id=row.session_id,
    )


@router.post("/api/job-descriptions", response_model=SaveJDResponse)
@limiter.limit("30/minute")
async def save_job_description(
    request: Request,
    body: SaveJDRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaveJDResponse:
    """Persist a job description from the extension and mint a Flint handoff token.

    Atomicity: ``db.flush()`` writes the JD row to the connection but does
    not commit. Commit is owned by the ``get_db`` dependency, which only
    runs after this function returns successfully. If ``create_jd_handoff_token``
    raises an HTTPException (for example a 503 on Redis collision), the
    surrounding rollback drops the JD row too — so callers either get back
    both a persisted JD AND a working token, or neither. This is the
    intended coupling: a JD without a token is unreachable from the
    "Open in Flint" flow, and a token without a JD is dangling state.
    """
    # Enforce the 20k-char cap server-side (extension may send raw DOM text).
    text = body.text[: settings.JD_TEXT_MAX_CHARS]

    jd = JobDescription(
        id=uuid.uuid4(),
        user_id=user.id,
        url=body.url or None,
        title=body.title or None,
        company=body.company or None,
        text=text,
        source=body.source,
    )
    db.add(jd)
    await db.flush()

    # Both the persisted row and the handoff payload use the same `text`
    # variable, so truncation applies consistently to storage and export.
    export_token, expires_in = await create_jd_handoff_token(
        jd_id=str(jd.id),
        jd_text=text,
        title=body.title,
        company=body.company,
        user_id=str(user.id),
    )

    return SaveJDResponse(
        jd_id=str(jd.id),
        export_token=export_token,
        expires_in=expires_in,
    )
