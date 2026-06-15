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
from app.services.flint_handoff import create_jd_handoff_token
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


@router.get("/api/job-descriptions/{jd_id}", response_model=JobDescriptionResponse)
@limiter.limit("60/minute")
async def get_job_description(
    request: Request,
    jd_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobDescriptionResponse:
    """Load an extension-saved JD for the tailoring wizard (Flint Resume web)."""
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
