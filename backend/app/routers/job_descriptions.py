"""Extension job description endpoints (Strategy B Phase 2).

``POST /api/job-descriptions`` saves a JD captured by the browser extension
and immediately mints a Flint handoff token so the user can open it in Flint.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

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


@router.post("/api/job-descriptions", response_model=SaveJDResponse)
@limiter.limit("30/minute")
async def save_job_description(
    request: Request,
    body: SaveJDRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaveJDResponse:
    """Persist a job description from the extension and mint a Flint handoff token."""
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
