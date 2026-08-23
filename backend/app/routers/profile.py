"""Master-resume profile router (Step 8 of IMPLEMENTATION_PLAN §6).

Six routes from the "Profile And Master Resume" table:

    POST   /api/profile/resume                  — upload or paste; chunk + embed
    GET    /api/profile/resume                  — raw text + parsed sections + last_embedded_at
    PUT    /api/profile/resume                  — full replace; re-embed all chunks
    PATCH  /api/profile/resume/chunks/{id}      — edit a single chunk; re-embed just that one
    DELETE /api/profile/resume/chunks/{id}      — soft delete
    GET    /api/profile/resume/chunks           — list; ?jd_session_id= returns similarity scores

Auth: every route requires a verified access JWT via ``get_current_user``.
Chunks are scoped by ``user_id`` so cross-tenant reads are impossible.

The structure-extraction LLM call mirrors ``app/routers/resume.py``
``_structure_resume``.  We deliberately reuse the existing ``ParsedResume``
schema to avoid drift between the session-resume path (used by the
unauthenticated demo flow) and the master-resume path.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.polish import polish_resume
from app.agent.story import story_to_resume
from app.agent.story_verify import build_verify_items
from app.agent.story_coach import MAX_EXCHANGES, coach_segment, is_complete_response
from app.agent.story_interview import (
    MAX_QUESTIONS,
    compile_answers_to_narrative,
    is_interview_complete,
    next_interview_question,
)
from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.llm.base import LLMMessage
from app.llm.factory import get_llm_client_for_step
from app.llm.structured import complete_structured
from app.models.master_resume import MasterResumeSectionType
from app.models.resume import ParsedResume
from app.models.story import (
    CoachMessage,
    CoachRequest,
    InterviewNextRequest,
    InterviewSubmitRequest,
    PolishResumeRequest,
    StorySaveRequest,
    StoryToResumeRequest,
    StoryVerifyRequest,
)
from app.models.user import User
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.text_parser import extract_text_from_txt
from app.services.auth.dependencies import get_current_user
from app.services.billing.quota import (
    check_quota_for_story_coach,
    check_quota_for_story_generate,
    check_quota_for_story_interview,
    check_quota_for_story_save,
)
from app.services.billing.exceptions import (
    AccountSuspendedError,
    CreditsLockedUntilVerificationError,
    InsufficientCreditsError,
)
from app.services.billing.credit_spend import credits_locked_detail
from app.services.resume_validation import validate_resume_text
from app.services.master_resume import crud as master_crud
from app.services.master_resume.chunking import Chunk, count_tokens
from app.services.master_resume.embedding import embed_text
from app.services.retrieval.config import RETRIEVAL_EMBEDDING_MODEL
from app.services.session_store import get_session as get_redis_session

log = structlog.get_logger("profile_router")

router = APIRouter(prefix="/api/profile", tags=["profile"])


ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ResumeTextBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=200_000)


class ChunkPatch(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000)
    section_type: MasterResumeSectionType | None = None
    metadata: dict[str, Any] | None = None


class BulkChunkItem(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000)
    section_type: MasterResumeSectionType = MasterResumeSectionType.experience
    metadata: dict[str, Any] | None = None


class BulkChunkInsert(BaseModel):
    chunks: list[BulkChunkItem] = Field(..., min_length=1, max_length=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _extract_resume_text(
    *,
    file: UploadFile | None,
    text_payload: str | None,
) -> str:
    """Parse the upload bytes (PDF/DOCX/TXT) or use the pasted text."""
    if file is not None:
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_MIME:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {content_type or 'unknown'}",
            )
        file_bytes = await file.read()
        if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=422,
                detail=f"File exceeds {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
            )
        if "pdf" in content_type:
            raw = extract_text_from_pdf(file_bytes)
        elif "wordprocessingml" in content_type:
            raw = extract_text_from_docx(file_bytes)
        else:
            raw = extract_text_from_txt(file_bytes)
    else:
        raw = (text_payload or "").strip()

    return validate_resume_text(raw)


async def _structure_with_llm(
    raw_text: str,
    *,
    provider: str | None,
    model: str | None,
) -> dict[str, Any]:
    """Best-effort LLM call to turn raw text into structured sections.

    Returns a dict suitable for ``parsed_sections`` storage.  Falls
    back to ``{}`` when no LLM key is available — the chunker has a
    raw-text fallback path that still produces useful chunks.
    """
    try:
        llm = get_llm_client_for_step("chat")
    except Exception as exc:
        log.warning("profile.llm.unavailable", error=str(exc))
        return {}

    messages = [
        LLMMessage(
            role="system",
            content=(
                "You are a resume parser. Extract the candidate's master resume "
                "into structured sections.  Return JSON matching the schema. "
                "If a field is missing, return empty string or empty list."
            ),
        ),
        LLMMessage(role="user", content=f"MASTER RESUME TEXT:\n{raw_text}"),
    ]
    try:
        parsed: ParsedResume = await complete_structured(llm, messages, ParsedResume)
    except Exception as exc:  # noqa: BLE001 — fall back to raw chunking
        log.warning("profile.llm.parse_failed", error=str(exc))
        return {}
    return _parsed_resume_to_sections(parsed)


def _parsed_resume_to_sections(parsed: ParsedResume) -> dict[str, Any]:
    """Project ``ParsedResume`` into the ``parsed_sections`` shape expected
    by the chunker.  Adapts field names where they differ (e.g. ``projects``
    → ``project``)."""
    sections: dict[str, Any] = {}
    data = parsed.model_dump()
    if data.get("summary"):
        sections["summary"] = data["summary"]
    if data.get("skills"):
        sections["skills"] = data["skills"]
    for key, dest in (
        ("experience", "experience"),
        ("projects", "project"),
        ("education", "education"),
        ("certifications", "cert"),
        ("publications", "publication"),
        ("awards", "award"),
        ("patents", "patent"),
        ("languages", "language"),
        ("volunteer", "volunteer"),
    ):
        value = data.get(key)
        if value:
            sections[dest] = value
    return sections


def _resume_to_response(resume) -> dict[str, Any]:
    return {
        "id": str(resume.id),
        "raw_text": resume.raw_text,
        "parsed_sections": resume.parsed_sections,
        "chunk_count": resume.chunk_count,
        "last_embedded_at": (
            resume.last_embedded_at.isoformat()
            if resume.last_embedded_at
            else None
        ),
        "created_at": resume.created_at.isoformat() if resume.created_at else None,
        "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/resume", status_code=200)
@limiter.limit("120/minute")
async def get_resume(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return the user's raw text + parsed sections + last_embedded_at."""
    resume = await master_crud.get_raw_resume(db, user_id=user.id)
    if resume is None:
        return {
            "id": None,
            "raw_text": "",
            "parsed_sections": {},
            "chunk_count": 0,
            "last_embedded_at": None,
            "created_at": None,
            "updated_at": None,
        }
    return _resume_to_response(resume)


@router.post("/resume/transcribe", status_code=200)
@limiter.limit("10/minute")
async def transcribe_resume_audio(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    audio: UploadFile = File(...),
):
    """Transcribe spoken resume audio to text using OpenAI Whisper.

    Gated by tier ``whisper_enabled`` / ``whisper_uses_per_period`` limits.
    """
    import io

    import openai

    from app.services.billing.exceptions import (
        AccountSuspendedError,
        PlanLimitReachedError,
        WhisperNotAllowedError,
    )
    from app.services.billing.whisper_gate import check_and_increment_whisper_use

    try:
        await check_and_increment_whisper_use(db, user=user)
    except AccountSuspendedError:
        raise HTTPException(status_code=403, detail={"code": "account_suspended"})
    except WhisperNotAllowedError:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "whisper_not_available",
                "message": "Whisper transcription requires a paid plan. Use Chrome/Edge live transcription or upgrade.",
            },
        )
    except PlanLimitReachedError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "plan_limit_reached",
                "action": exc.action,
                "used": exc.used,
                "limit": exc.limit,
            },
        )

    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail=(
                "Voice transcription is not available — platform OpenAI key is not configured."
            ),
        )

    audio_bytes = await audio.read()
    max_bytes = 25 * 1024 * 1024  # Whisper API limit
    if len(audio_bytes) > max_bytes:
        raise HTTPException(status_code=422, detail="Audio file exceeds the 25 MB Whisper limit.")

    content_type = (audio.content_type or "audio/webm").lower()
    # Map MIME → extension that Whisper accepts
    _ext: dict[str, str] = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "mp4",
        "audio/x-m4a": "m4a",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
    }
    ext = _ext.get(content_type, "webm")
    filename = f"recording.{ext}"

    client = openai.AsyncOpenAI(api_key=api_key)
    try:
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, io.BytesIO(audio_bytes), content_type),
            language="en",
        )
    except openai.AuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail="OpenAI authentication failed — check your API key.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {exc}",
        ) from exc

    return {"text": transcript.text}


@router.post("/resume", status_code=201)
@limiter.limit("30/minute")
async def create_or_replace_resume(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_model: str | None = Header(default=None, alias="X-Model"),
):
    """Upload or paste the master resume — chunks + embeds the entire payload.

    This is the create path used by the ``/profile`` page.  The PUT
    variant below is the explicit "full replace" verb; the two
    handlers share the same implementation because §18.4 specifies the
    same chunking + embedding pipeline for both.
    """
    if file is None and not text:
        raise HTTPException(
            status_code=422,
            detail="Provide either a file upload or a non-empty 'text' form field.",
        )

    raw = await _extract_resume_text(file=file, text_payload=text)
    parsed_sections = await _structure_with_llm(
        raw, provider=x_provider, model=x_model
    )
    resume, chunks = await master_crud.replace_all_chunks(
        db,
        user_id=user.id,
        raw_text=raw,
        parsed_sections=parsed_sections,
    )
    embedding_ok = resume.last_embedded_at is not None
    log.info(
        "profile.resume.replaced",
        user_id=str(user.id),
        chunk_count=len(chunks),
        had_parsed_sections=bool(parsed_sections),
        embedding_ok=embedding_ok,
    )
    return {
        **_resume_to_response(resume),
        "chunks": master_crud.iter_chunk_summaries(chunks),
        "embedding_warning": (
            None if embedding_ok
            else "Resume saved but embedding failed (OpenAI key missing or invalid). "
                 "Semantic similarity features won't work until OPENAI_EMBEDDING_KEY is configured."
        ),
    }


@router.put("/resume", status_code=200)
@limiter.limit("30/minute")
async def replace_resume(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_model: str | None = Header(default=None, alias="X-Model"),
):
    """Full replace: same shape as POST but always re-embeds every chunk."""
    return await create_or_replace_resume(
        request=request,
        user=user,
        db=db,
        file=file,
        text=text,
        x_provider=x_provider,
        x_model=x_model,
    )


@router.get("/resume/chunks", status_code=200)
@limiter.limit("120/minute")
async def list_chunks(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    jd_session_id: str | None = Query(default=None),
    section_type: MasterResumeSectionType | None = Query(default=None),
):
    """List all live chunks; optionally include similarity vs a session's JD.

    When ``jd_session_id`` resolves to a session with a non-empty
    ``jd_raw``, we embed the JD here (cached LRU) and run the cosine
    against every returned chunk so the UI can show "this chunk has
    similarity 0.81 against the JD you're working on right now".
    """
    chunks = await master_crud.get_chunks_for_user(
        db, user_id=user.id, section_type=section_type
    )
    summaries = master_crud.iter_chunk_summaries(chunks)

    if jd_session_id:
        await _attach_similarity_scores(summaries, chunks, jd_session_id)

    return {"chunks": summaries}


async def _attach_similarity_scores(
    summaries: list[dict[str, Any]],
    rows,
    jd_session_id: str,
) -> None:
    """Compute cosine similarity vs a session's JD and inject into summaries."""
    redis_session = await get_redis_session(jd_session_id)
    if redis_session is None or not (redis_session.jd_raw or "").strip():
        return

    try:
        jd_vec = await embed_text(
            redis_session.jd_raw, model=RETRIEVAL_EMBEDDING_MODEL
        )
    except Exception as exc:  # noqa: BLE001 — best effort; UI just skips badges
        log.warning("profile.chunks.embed_jd_failed", error=str(exc))
        return

    for summary, row in zip(summaries, rows):
        if row.embedding is None:
            summary["score"] = None
            continue
        summary["score"] = _cosine(jd_vec, row.embedding)


def _cosine(a, b) -> float:
    """Plain-Python cosine between two iterables.

    Accepts lists, tuples, or numpy arrays (pgvector returns the latter
    via the SQLAlchemy adapter).  We never use array-truthiness checks
    because that raises ``ValueError`` on numpy inputs.
    """
    import math

    if a is None or b is None:
        return 0.0
    try:
        a_iter = list(a)
        b_iter = list(b)
    except TypeError:
        return 0.0
    if not a_iter or not b_iter:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a_iter, b_iter):
        x = float(x)
        y = float(y)
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return round(dot / (math.sqrt(na) * math.sqrt(nb)), 6)


@router.patch("/resume/chunks", status_code=200)
@limiter.limit("30/minute")
async def bulk_insert_chunks(
    request: Request,
    body: BulkChunkInsert,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk-insert new master resume chunks (e.g. suggested bullets from fit analysis)."""
    chunk_models = [
        Chunk(
            section_type=item.section_type,
            content=item.content.strip(),
            token_count=count_tokens(item.content),
            metadata=dict(item.metadata or {}),
        )
        for item in body.chunks
    ]
    try:
        rows = await master_crud.add_chunks(db, user_id=user.id, chunks=chunk_models)
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail={"code": "master_resume_required"},
        ) from None
    return {"chunks": master_crud.iter_chunk_summaries(rows)}


@router.patch("/resume/chunks/{chunk_id}", status_code=200)
@limiter.limit("30/minute")
async def patch_chunk(
    request: Request,
    chunk_id: str,
    body: ChunkPatch,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        chunk_uuid = uuid.UUID(chunk_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chunk id.") from None

    updated = await master_crud.update_chunk_content(
        db,
        user_id=user.id,
        chunk_id=chunk_uuid,
        new_content=body.content,
        new_section_type=body.section_type,
        new_metadata=body.metadata,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    return {
        "chunk": master_crud.iter_chunk_summaries([updated])[0],
    }


@router.delete("/resume/chunks/{chunk_id}", status_code=200)
@limiter.limit("30/minute")
async def delete_chunk(
    request: Request,
    chunk_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        chunk_uuid = uuid.UUID(chunk_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chunk id.") from None

    deleted = await master_crud.delete_chunk(
        db, user_id=user.id, chunk_id=chunk_uuid
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    return {"deleted": True, "id": chunk_id}


@router.post("/resume/from-story", status_code=200)
@limiter.limit("5/minute")
async def create_resume_from_story(
    request: Request,
    body: StoryToResumeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Convert a spoken career narrative to a resume draft for review.

    Does NOT write to the master profile — call POST /resume/from-story/save
    after the user verifies names and dates.

    Credit rules: first generate free; regenerates cost 1 credit (subscribers free).
    """
    provider = request.headers.get("X-Provider", "").strip()
    model = request.headers.get("X-Model", "").strip()
    story_session_id = request.headers.get("X-Story-Session-Id", "").strip() or None

    llm_client = get_llm_client_for_step("story")

    try:
        billing = await check_quota_for_story_generate(
            db,
            user=user,
            whisper_path=body.whisper_path,
            session_id=story_session_id,
        )
    except CreditsLockedUntilVerificationError as exc:
        raise HTTPException(
            status_code=403,
            detail=credits_locked_detail(balance=exc.balance),
        ) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "insufficient_credits",
                "message": "Regenerating from your story costs 1 credit.",
            },
        ) from exc

    narrative = "\n\n---\n\n".join(seg.strip() for seg in body.segments if seg.strip())

    try:
        draft_text = await story_to_resume(narrative, llm_client)
    except Exception as exc:
        log.error("story.convert_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"code": "story_conversion_failed", "message": str(exc)},
        ) from exc

    verify_items = [item.to_dict() for item in build_verify_items(body.segments, draft_text)]
    review_count = sum(1 for item in verify_items if item["status"] == "review")

    log.info(
        "story.draft_generated",
        user_id=str(user.id),
        draft_chars=len(draft_text),
        verify_review_count=review_count,
        charged_to=billing.charged_to,
    )
    return {
        "resume_text": draft_text,
        "verify_items": verify_items,
        "verify_review_count": review_count,
        "billing": {
            "charged_to": billing.charged_to,
            "action": billing.action.value,
        },
    }


@router.post("/resume/story-verify", status_code=200)
@limiter.limit("30/minute")
async def story_verify_draft(
    request: Request,
    body: StoryVerifyRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Recompute verify hints after the user edits the draft text."""
    verify_items = [item.to_dict() for item in build_verify_items(body.segments, body.resume_text)]
    return {
        "verify_items": verify_items,
        "verify_review_count": sum(1 for item in verify_items if item["status"] == "review"),
    }


@router.post("/resume/from-story/save", status_code=200)
@limiter.limit("5/minute")
async def save_resume_from_story(
    request: Request,
    body: StorySaveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Save a reviewed story resume to the master profile.

    Requires attestation. First save free; later saves cost 1 credit (subscribers free).
    """
    provider = request.headers.get("X-Provider", "").strip()
    model = request.headers.get("X-Model", "").strip()
    story_session_id = request.headers.get("X-Story-Session-Id", "").strip() or None

    try:
        billing = await check_quota_for_story_save(
            db,
            user=user,
            session_id=story_session_id,
        )
    except CreditsLockedUntilVerificationError as exc:
        raise HTTPException(
            status_code=403,
            detail=credits_locked_detail(balance=exc.balance),
        ) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "insufficient_credits",
                "message": "Saving your story resume costs 1 credit.",
            },
        ) from exc

    draft_text = body.resume_text.strip()
    parsed_sections = await _structure_with_llm(
        draft_text, provider=provider or None, model=model or None
    )
    try:
        resume, chunks = await master_crud.replace_all_chunks(
            db,
            user_id=user.id,
            raw_text=draft_text,
            parsed_sections=parsed_sections,
        )
    except Exception as exc:
        log.error("story.save_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"code": "parse_failed", "message": str(exc)},
        ) from exc

    embedding_ok = resume.last_embedded_at is not None
    log.info(
        "story.resume_saved",
        user_id=str(user.id),
        chunk_count=len(chunks),
        embedding_ok=embedding_ok,
        charged_to=billing.charged_to,
    )
    return {
        **_resume_to_response(resume),
        "chunks": master_crud.iter_chunk_summaries(chunks),
        "resume_text": draft_text,
        "embedding_warning": (
            None if embedding_ok
            else "Resume saved but embedding failed. Semantic similarity features won't work "
                 "until OPENAI_EMBEDDING_KEY is configured."
        ),
        "billing": {
            "charged_to": billing.charged_to,
            "action": billing.action.value,
        },
    }


@router.post("/resume/polish", status_code=200)
@limiter.limit("30/minute")
async def polish_resume_draft(
    request: Request,
    body: PolishResumeRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """
    Apply a single plain-English editing instruction to a resume draft.

    Used by the Story Mode review step.  No credit is charged: this is
    a free iteration on a story_build that already cost 1 credit.

    Returns: { "text": "<updated resume text>" }
    """
    provider = request.headers.get("X-Provider", "").strip()
    model = request.headers.get("X-Model", "").strip()

    llm_client = get_llm_client_for_step("polish")

    try:
        updated = await polish_resume(body.text, body.instruction, llm_client)
    except Exception as exc:
        log.error("polish.failed", error=str(exc), user_id=str(user.id))
        raise HTTPException(
            status_code=502,
            detail={"code": "polish_failed", "message": str(exc)},
        ) from exc

    return {"text": updated}


@router.post("/story/coach", status_code=200)
@limiter.limit("10/minute")
async def story_coach_endpoint(
    request: Request,
    body: CoachRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream one follow-up question from the interview coach (§22).

    - Subscribers: 0 credits.
    - Free users: 1 credit per story build session (deducted on the first
      coached segment when history is empty).  Further segments in the same
      session_id reuse that credit.  Requires session_id for free platform users.
    - Max {MAX_EXCHANGES} exchanges per segment enforced here.

    Returns: SSE stream of {"delta": str} events, finished by {"done": true}.
    """
    # Rate-limit abuse: cap exchanges server-side as well as client-side
    prior_coach_msgs = [m for m in body.history if m.role == "coach"]
    if len(prior_coach_msgs) >= MAX_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "coach_limit_reached",
                "message": f"Maximum {MAX_EXCHANGES} coaching exchanges per segment.",
            },
        )

    provider = request.headers.get("X-Provider", "").strip()
    model = request.headers.get("X-Model", "").strip()

    # Charge 1 credit on the first coached segment of a story build session.
    if not body.history:
        if not body.session_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "session_id_required",
                    "message": "Story build session ID is required for coaching.",
                },
            )
        try:
            await check_quota_for_story_coach(
                session,
                user=user,
                session_id=body.session_id,
            )
        except AccountSuspendedError:
            raise HTTPException(status_code=403, detail={"code": "account_suspended"})
        except CreditsLockedUntilVerificationError as exc:
            raise HTTPException(
                status_code=403,
                detail=credits_locked_detail(balance=exc.balance),
            ) from exc
        except InsufficientCreditsError:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "insufficient_credits",
                    "message": "You need at least 1 credit to start a coaching session.",
                },
            )
        await session.commit()

    llm_client = get_llm_client_for_step("story_coach")

    history_dicts = [{"role": m.role, "text": m.text} for m in body.history]

    import json

    async def _generate():
        buffer = ""
        try:
            async for delta in coach_segment(
                segment_text=body.segment_text,
                history=history_dicts,
                llm_client=llm_client,
            ):
                buffer += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as exc:  # noqa: BLE001
            log.error("story_coach.stream_error", error=str(exc))
            yield 'data: {"error": "coach_failed"}\n\n'
            return

        complete = is_complete_response(buffer)
        yield f"data: {json.dumps({'done': True, 'complete': complete})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.post("/story/interview/next", status_code=200)
@limiter.limit("20/minute")
async def story_interview_next(
    request: Request,
    body: InterviewNextRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the next interview question (Coached Interview Mode, §23).

    - Subscribers: 0 credits.
    - Free users: 1 credit charged on the very first question (empty history).
    - Server-side cap: MAX_QUESTIONS per session.

    Returns SSE stream: {"delta": str} events, then {"done": true, "complete": bool}.
    ``complete=true`` means the LLM emitted INTERVIEW_COMPLETE — client should
    stop asking for questions and call POST /story/interview/submit.
    """
    prior_questions = [m for m in body.history if m.role == "interviewer"]
    if len(prior_questions) >= MAX_QUESTIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "interview_limit_reached",
                "message": f"Maximum {MAX_QUESTIONS} interview questions reached. Please submit your answers.",
            },
        )

    provider = request.headers.get("X-Provider", "").strip()
    model = request.headers.get("X-Model", "").strip()

    # Charge 1 credit on the very first question (history is empty)
    if not body.history:
        try:
            await check_quota_for_story_interview(
                session,
                user=user,
                session_id=body.session_id,
            )
        except AccountSuspendedError:
            raise HTTPException(status_code=403, detail={"code": "account_suspended"})
        except CreditsLockedUntilVerificationError as exc:
            raise HTTPException(
                status_code=403,
                detail=credits_locked_detail(balance=exc.balance),
            ) from exc
        except InsufficientCreditsError:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "insufficient_credits",
                    "message": "You need at least 1 credit to start a coached interview session.",
                },
            )
        await session.commit()

    llm_client = get_llm_client_for_step("story_interview")

    history_dicts = [{"role": m.role, "text": m.text} for m in body.history]

    import json as _json

    async def _generate():
        buffer = ""
        try:
            async for delta in next_interview_question(history_dicts, llm_client):
                buffer += delta
                yield f"data: {_json.dumps({'delta': delta})}\n\n"
        except Exception as exc:  # noqa: BLE001
            log.error("story_interview.stream_error", error=str(exc))
            yield 'data: {"error": "interview_failed"}\n\n'
            return

        complete = is_interview_complete(buffer)
        yield f"data: {_json.dumps({'done': True, 'complete': complete})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.post("/story/interview/submit", status_code=200)
@limiter.limit("5/minute")
async def story_interview_submit(
    request: Request,
    body: InterviewSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Compile interview Q&A and generate resume (Coached Interview Mode, §23).

    Compiles all interview answers into a narrative and runs the same
    story_to_resume → master resume pipeline as POST /resume/from-story.
    The interview session credit was already charged by /story/interview/next;
    this endpoint does NOT charge an additional credit.

    Returns the same shape as POST /resume/from-story.
    """
    provider = request.headers.get("X-Provider", "").strip()
    model = request.headers.get("X-Model", "").strip()

    history_dicts = [{"role": m.role, "text": m.text} for m in body.history]
    narrative = compile_answers_to_narrative(history_dicts)

    log.info(
        "story_interview.submit",
        user_id=str(user.id),
        narrative_chars=len(narrative),
        exchange_count=len(body.history),
    )

    llm_client = get_llm_client_for_step("story_verify")

    try:
        draft_text = await story_to_resume(narrative, llm_client)
    except Exception as exc:  # noqa: BLE001
        log.error("story_interview.story_to_resume_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"code": "interview_generation_failed", "message": str(exc)},
        ) from exc

    user_segments = [m.text for m in body.history if m.role == "user" and m.text.strip()]
    verify_items = [item.to_dict() for item in build_verify_items(user_segments, draft_text)]
    review_count = sum(1 for item in verify_items if item["status"] == "review")

    log.info(
        "story_interview.draft_generated",
        user_id=str(user.id),
        verify_review_count=review_count,
    )
    return {
        "resume_text": draft_text,
        "verify_items": verify_items,
        "verify_review_count": review_count,
        "billing": {
            "charged_to": "interview_session_included",
            "action": "story_interview",
        },
    }


__all__ = ["router"]
