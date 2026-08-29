from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.llm.base import LLMMessage
from app.llm.factory import get_llm_client_for_step
from app.llm.token_accounting import llm_accounting_context
from app.llm.structured import complete_structured
from app.models.job_description import JobDescription
from app.models.resume import ParsedResume
from app.models.session import BulletFix
from app.models.userinfo import UserInfo
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.text_parser import extract_text_from_txt
from app.services.bullet_fix_suggest import (
    BulletFixSuggestionItem,
    suggest_bullet_fixes,
)
from app.services.auth.dependencies import assert_user_email_verified
from app.services.session_ownership import resolve_bearer_user_id
from app.services.resume_validation import validate_resume_text
from app.services.session_store import get_session, update_session

router = APIRouter(prefix="/api/sessions", tags=["resume"])

ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


class ResumeTextRequest(BaseModel):
    text: str


class JDRequest(BaseModel):
    jd_text: str
    jd_url: str | None = None
    provider: str | None = None
    model: str | None = None
    # When provided, the JobDescription row is updated so subsequent visits
    # from the extension can detect and reopen the existing session.
    jd_id: str | None = None


async def _structure_resume(raw_text: str, llm) -> ParsedResume:
    """Use an LLM call to structure raw resume text into ParsedResume."""
    messages = [
        LLMMessage(
            role="system",
            content=(
                "You are a resume parser. Extract the structured data from the following resume text "
                "and return it as valid JSON conforming exactly to the given schema. "
                "If a field is not found, use an empty string or empty list."
            ),
        ),
        LLMMessage(role="user", content=f"RESUME TEXT:\n{raw_text}"),
    ]
    return await complete_structured(llm, messages, ParsedResume)


async def _require_verified_llm_user(
    db: AsyncSession,
    session,
    authorization: str | None,
) -> None:
    """Block LLM spend for authenticated users who have not verified email."""
    user_id = await resolve_bearer_user_id(authorization, session)
    if user_id:
        await assert_user_email_verified(db, user_id)


@router.post("/{session_id}/resume")
@limiter.limit("10/minute")
async def upload_resume(
    request: Request,
    session_id: str,
    file: UploadFile = File(...),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    authorization: str | None = Header(default=None),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await _require_verified_llm_user(db, session, authorization)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="File exceeds 5MB limit.")

    if "pdf" in content_type:
        raw_text = extract_text_from_pdf(file_bytes)
    elif "wordprocessingml" in content_type:
        raw_text = extract_text_from_docx(file_bytes)
    else:
        raw_text = extract_text_from_txt(file_bytes)

    raw_text = validate_resume_text(raw_text)

    with llm_accounting_context(
        session_id, "resume_structure", user_id=session.user_id
    ):
        llm = get_llm_client_for_step("resume_structure")
        parsed = await _structure_resume(raw_text, llm)

    session.resume_raw = raw_text
    session.resume_parsed = parsed
    await update_session(session)
    from app.services.dashboard.resume_record import sync_dashboard_record_from_session

    await sync_dashboard_record_from_session(session)
    return {"parsed": parsed.model_dump()}


@router.post("/{session_id}/resume/text")
@limiter.limit("10/minute")
async def paste_resume(
    request: Request,
    session_id: str,
    body: ResumeTextRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    authorization: str | None = Header(default=None),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await _require_verified_llm_user(db, session, authorization)

    text = validate_resume_text(body.text)

    with llm_accounting_context(
        session_id, "resume_structure", user_id=session.user_id
    ):
        llm = get_llm_client_for_step("resume_structure")
        parsed = await _structure_resume(text, llm)

    session.resume_raw = text
    session.resume_parsed = parsed
    await update_session(session)
    from app.services.dashboard.resume_record import sync_dashboard_record_from_session

    await sync_dashboard_record_from_session(session)
    return {"parsed": parsed.model_dump()}


@router.post("/{session_id}/userinfo")
async def save_userinfo(
    session_id: str,
    body: UserInfo,
    db: Annotated[AsyncSession, Depends(get_db)],
    jd_id: str | None = Query(default=None),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.user_info = body
    await update_session(session)
    from app.services.dashboard.resume_record import sync_dashboard_record_from_session

    await sync_dashboard_record_from_session(session)

    # Link extension-saved JD only after wizard info step — not on JD submit alone.
    if jd_id and session.user_id:
        try:
            jd_uuid = uuid.UUID(jd_id)
            row = (
                await db.execute(
                    select(JobDescription).where(
                        JobDescription.id == jd_uuid,
                        JobDescription.user_id == uuid.UUID(session.user_id),
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                row.session_id = session_id
        except (ValueError, Exception):
            pass

    return {"ok": True}


class AdditionsRequest(BaseModel):
    claimed_keywords: list[str] = []
    extra_notes: str = ""
    # Fix 4: persist user-supplied bullet corrections.
    bullet_fixes: list[BulletFix] = []


class SuggestBulletFixesRequest(BaseModel):
    indices: list[int]


class SuggestBulletFixesResponse(BaseModel):
    fixes: list[BulletFixSuggestionItem]


@router.post("/{session_id}/audit/suggest-bullet-fixes", response_model=SuggestBulletFixesResponse)
@limiter.limit("20/minute")
async def suggest_audit_bullet_fixes(
    request: Request,
    session_id: str,
    body: SuggestBulletFixesRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    authorization: str | None = Header(default=None),
) -> SuggestBulletFixesResponse:
    """Generate AI rewrite suggestions for selected Phase 2 bullet issues."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    audit = session.phase2_output
    if audit is None or not audit.bullet_issues:
        raise HTTPException(status_code=422, detail="Run the resume audit first.")
    if not body.indices:
        raise HTTPException(status_code=422, detail="Select at least one bullet to fix.")

    await _require_verified_llm_user(db, session, authorization)

    with llm_accounting_context(
        session_id, "mechanical_fixes", user_id=session.user_id
    ):
        llm = get_llm_client_for_step("mechanical_fixes")
        fixes = await suggest_bullet_fixes(
            llm,
            session=session,
            issues=audit.bullet_issues,
            indices=body.indices,
        )
    return SuggestBulletFixesResponse(fixes=fixes)


def _enqueue_corpus_additions(session: object, body: "AdditionsRequest") -> None:  # type: ignore[name-defined]
    """Fire-and-forget: embed notes and claimed keywords into the corpus."""
    if not settings.DATABASE_URL.strip():
        return

    user_id_str = getattr(session, "user_id", None)
    if not user_id_str:
        return

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return

    session_id = getattr(session, "session_id", None)

    from app.services.corpus_writer import embed_claimed_keywords, embed_user_notes

    notes = (getattr(body, "extra_notes", None) or "").strip()
    keywords = list(getattr(body, "claimed_keywords", None) or [])

    if notes:
        asyncio.create_task(
            embed_user_notes(
                user_id=user_id,
                session_id=session_id,
                notes_text=notes,
            ),
            name=f"corpus_notes:{session_id}",
        )

    if keywords:
        asyncio.create_task(
            embed_claimed_keywords(
                user_id=user_id,
                session_id=session_id,
                keywords=keywords,
            ),
            name=f"corpus_kw:{session_id}",
        )


@router.patch("/{session_id}/additions")
async def save_additions(session_id: str, body: AdditionsRequest):
    """Save keywords/skills the user claims to have that weren't in the original resume,
    plus optional free-text notes and per-bullet fix suggestions."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.user_claimed_keywords = body.claimed_keywords
    session.user_extra_notes = body.extra_notes
    session.bullet_fixes = body.bullet_fixes
    await update_session(session)

    # Corpus expansion: embed notes and claimed keywords in the background
    # so future sessions can retrieve them as personal context.
    _enqueue_corpus_additions(session, body)

    return {"ok": True, "claimed": len(body.claimed_keywords)}


@router.post("/{session_id}/jd")
async def submit_jd(
    session_id: str,
    body: JDRequest,
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    import httpx
    from app.parsers.html_parser import strip_html_to_text

    jd_text = body.jd_text
    if body.jd_url and not jd_text:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    body.jd_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; TalioCV/1.0)"},
                )
                jd_text = strip_html_to_text(resp.text, max_chars=settings.MAX_JD_CHARS)
        except Exception:
            raise HTTPException(status_code=422, detail="Could not fetch JD from URL.")

        # Catch JS-rendered pages that return a thin HTML shell with no
        # readable text (Jobright, Greenhouse, Lever, etc.).
        if len(jd_text.strip()) < 200:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The job board page couldn't be scraped — it uses JavaScript rendering "
                    "and returned no readable text. Please copy and paste the job description "
                    "text directly into the JD field instead."
                ),
            )

    # Strip HTML even from manually-pasted text (belt-and-suspenders).
    if jd_text:
        jd_text = strip_html_to_text(jd_text, max_chars=settings.MAX_JD_CHARS)

    if len(jd_text) > settings.MAX_JD_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Job description exceeds {settings.MAX_JD_CHARS:,} characters. Paste only the requirements section.",
        )

    jd_changed = (session.jd_raw or "").strip() != jd_text.strip()
    session.jd_raw = jd_text
    # `body.provider` / `body.model` are accepted for wire compatibility with
    # older clients but deliberately not stored: model choice comes from the
    # step registry, never from the caller.

    # If the JD changed, all phase outputs are stale — wipe them so the
    # user is not misled by results computed from the old job description.
    if jd_changed:
        session.phase1_output = None
        session.phase2_output = None
        session.phase3_output = None
        session.phase4_output = None
        session.phase3_stale_since = None
        session.phase4_stale_since = None

    await update_session(session)
    from app.services.dashboard.resume_record import sync_dashboard_record_from_session

    await sync_dashboard_record_from_session(session)

    return {"ok": True, "jd_changed": jd_changed}
