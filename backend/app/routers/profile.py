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
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.llm.base import LLMMessage
from app.llm.factory import get_llm_client
from app.llm.structured import complete_structured
from app.models.master_resume import MasterResumeSectionType
from app.models.resume import ParsedResume
from app.models.user import User
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.text_parser import extract_text_from_txt
from app.services.auth.dependencies import get_current_user
from app.services.master_resume import crud as master_crud
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

    if not raw:
        raise HTTPException(
            status_code=422,
            detail="Master resume is empty — provide a file or non-empty text.",
        )
    if len(raw) > settings.MAX_RESUME_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Master resume exceeds {settings.MAX_RESUME_CHARS:,} characters. "
                "Trim older or irrelevant experience."
            ),
        )
    return raw


async def _structure_with_llm(
    raw_text: str,
    *,
    api_key: str | None,
    provider: str | None,
    model: str | None,
) -> dict[str, Any]:
    """Best-effort LLM call to turn raw text into structured sections.

    Returns a dict suitable for ``parsed_sections`` storage.  Falls
    back to ``{}`` when no LLM key is available — the chunker has a
    raw-text fallback path that still produces useful chunks.
    """
    try:
        llm = get_llm_client(provider, model, api_key=api_key)
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


@router.post("/resume", status_code=201)
@limiter.limit("30/minute")
async def create_or_replace_resume(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
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
        raw, api_key=x_api_key, provider=x_provider, model=x_model
    )
    resume, chunks = await master_crud.replace_all_chunks(
        db,
        user_id=user.id,
        raw_text=raw,
        parsed_sections=parsed_sections,
    )
    log.info(
        "profile.resume.replaced",
        user_id=str(user.id),
        chunk_count=len(chunks),
        had_parsed_sections=bool(parsed_sections),
    )
    return {
        **_resume_to_response(resume),
        "chunks": master_crud.iter_chunk_summaries(chunks),
    }


@router.put("/resume", status_code=200)
@limiter.limit("30/minute")
async def replace_resume(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
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
        x_api_key=x_api_key,
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


__all__ = ["router"]
