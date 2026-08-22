from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import chat as chat_agent
from app.db.engine import get_db
from app.limiter import limiter
from app.llm.factory import get_llm_client
from app.models.chat import ChatRequest, ChatResponse
from app.models.dashboard import ResumeRecord
from app.services.dashboard.resume_record import resolve_company_name
from app.models.rewrite import TailoredResumeOutput
from app.models.session import ApprovedMetric
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.session_ownership import (
    bind_session_user_from_bearer,
    bearer_claims_or_none,
    resolve_bearer_user_id,
)
from app.services.session_store import create_session, get_session, update_session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionResumeRecordResponse(BaseModel):
    id: uuid.UUID
    display_name: str | None
    jd_title: str
    jd_company: str
    tailoring_stage: str


@router.post("", status_code=201)
@limiter.limit("20/minute")
async def new_session(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    session = await create_session()
    await bind_session_user_from_bearer(authorization, session)
    return {"session_id": session.session_id}


@router.get("/{session_id}")
async def check_session(session_id: str):
    """Existence check + resume text and cached phase outputs for UI hydration."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    def phase_payload(n: int) -> dict:
        status = getattr(session, f"phase{n}_status")
        output = getattr(session, f"phase{n}_output")
        return {
            "status": status.value if hasattr(status, "value") else status,
            "output": json.loads(output.model_dump_json()) if output is not None else None,
        }

    phases_out = {
        "1": phase_payload(1),
        "2": phase_payload(2),
        "3": phase_payload(3),
        "4": phase_payload(4),
    }

    stale: dict[str, str | None] = {
        "3": session.phase3_stale_since.isoformat() if session.phase3_stale_since else None,
        "4": session.phase4_stale_since.isoformat() if session.phase4_stale_since else None,
    }

    has_jd = bool((session.jd_raw or "").strip())
    export_company: str | None = None
    if has_jd:
        company = resolve_company_name(session)
        if company and company not in ("Unknown", "—"):
            export_company = company

    return {
        "session_id": session.session_id,
        "ok": True,
        "resume_raw": session.resume_raw or "",
        "has_jd": has_jd,
        "export_company": export_company,
        "phases": phases_out,
        "cover_letter": (
            json.loads(session.cover_letter_output.model_dump_json())
            if session.cover_letter_output is not None
            else None
        ),
        "stale": stale,
        "stale_since": session.stale_since.isoformat() if session.stale_since else None,
        "phase1_complete": session.phase1_status.value == "done",
        "has_user_info": session.user_info is not None,
        "resume_parsed": (
            json.loads(session.resume_parsed.model_dump_json())
            if session.resume_parsed is not None
            else None
        ),
        # Fix 2: expose user additions so the UI can survive a full page refresh.
        "user_claimed_keywords": session.user_claimed_keywords,
        "user_extra_notes": session.user_extra_notes,
        "bullet_fixes": [bf.model_dump() for bf in session.bullet_fixes],
        "approved_metrics": [am.model_dump() for am in (session.approved_metrics or [])],
    }


class TailoredEditRequest(BaseModel):
    tailored_output: dict


class ApprovedMetricsRequest(BaseModel):
    approved_metrics: list[ApprovedMetric]


@router.patch("/{session_id}/approved-metrics")
async def save_approved_metrics(session_id: str, body: ApprovedMetricsRequest):
    """Persist the user-verified metrics list before Phase 3 runs.

    Replaces the full approved_metrics list on the session — the UI always
    sends the complete current state, not a delta.  Phase 3 will only embed
    numbers that appear in this list; everything else goes to metrics_needed.
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.approved_metrics = body.approved_metrics
    await update_session(session)
    return {"ok": True, "count": len(body.approved_metrics)}


@router.patch("/{session_id}/tailored")
async def save_tailored_edits(session_id: str, body: TailoredEditRequest):
    """Persist user-edited tailored resume (overwrites phase3_output)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        session.phase3_output = TailoredResumeOutput.model_validate(body.tailored_output)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid tailored output: {exc}") from exc
    await update_session(session)
    return {"ok": True}


class CommitTailoredRequest(BaseModel):
    tailored_output: dict


@router.post("/{session_id}/tailored/commit")
async def commit_tailored_edits(
    session_id: str,
    body: CommitTailoredRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Save polished resume and sync master resume + RAG corpus (name, dates, titles)."""
    from app.services.tailored_persistence import commit_tailored_resume

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        tailored = TailoredResumeOutput.model_validate(body.tailored_output)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid tailored output: {exc}") from exc

    account_email: str | None = None
    claims = bearer_claims_or_none(authorization)
    if claims:
        account_email = claims.get("email")
    user_id = await resolve_bearer_user_id(authorization, session)
    await commit_tailored_resume(
        session_id,
        tailored,
        user_id=user_id,
        account_email=account_email,
    )
    return {"ok": True}


@router.post("/{session_id}/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_with_resume(
    request: Request, session_id: str, body: ChatRequest
) -> ChatResponse:
    """Free-form chat to request targeted resume edits. Returns a reply and structured patches."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Use the session's provider/model so chat works the same LLM
    # the user already configured for their phase runs.
    llm = get_llm_client(
        provider=session.provider or None,
        model=session.model or None,
    )
    return await chat_agent.run(session, body, llm)


@router.get("/{session_id}/resume-record", response_model=SessionResumeRecordResponse)
async def get_session_resume_record(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResumeRecordResponse:
    """Dashboard row linked to this tailoring session, if any."""
    record = (
        await db.execute(
            select(ResumeRecord).where(
                ResumeRecord.user_id == user.id,
                ResumeRecord.session_id == session_id,
                ResumeRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Resume record not found")
    return SessionResumeRecordResponse(
        id=record.id,
        display_name=record.display_name,
        jd_title=record.jd_title,
        jd_company=record.jd_company,
        tailoring_stage=record.tailoring_stage.value,
    )
