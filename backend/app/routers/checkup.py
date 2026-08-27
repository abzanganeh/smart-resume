"""Public resume checkup endpoint (M13 Step 42)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter, rate_limit_key
from app.llm.factory import get_llm_client_for_step
from app.llm.token_accounting import llm_accounting_context
from app.models.qa import QAOutput
from app.models.user import User
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.text_parser import extract_text_from_txt
from app.routers.resume import _structure_resume
from app.services.auth.client_ip import resolve_client_ip
from app.services.auth.tokens import TokenExpiredError, TokenInvalidError, decode_access_token
from app.services.checkup_limits import (
    checkup_result_cache_key,
    enforce_anonymous_checkup_device_cap,
    enforce_signed_in_checkup_quota,
    load_cached_checkup_result,
    store_cached_checkup_result,
)
from app.services.checkup_service import run_checkup_analysis

router = APIRouter(prefix="/api/checkup", tags=["checkup"])

ALLOWED_RESUME_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


class CheckupResponse(BaseModel):
    result: QAOutput


def _optional_authenticated_user_id(authorization: str | None) -> uuid.UUID | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        claims = decode_access_token(token, expected_type="access")
        return uuid.UUID(str(claims["sub"]))
    except (TokenExpiredError, TokenInvalidError, ValueError, KeyError):
        return None


async def _extract_resume_text(
    *,
    resume_text: str | None,
    file: UploadFile | None,
) -> str:
    text = (resume_text or "").strip()
    if file is not None:
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_RESUME_MIME:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported resume file type: {content_type or 'unknown'}",
            )
        file_bytes = await file.read()
        if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="Resume file exceeds upload limit.")
        if "pdf" in content_type:
            text = extract_text_from_pdf(file_bytes)
        elif "wordprocessingml" in content_type:
            text = extract_text_from_docx(file_bytes)
        else:
            text = extract_text_from_txt(file_bytes)

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Resume text is empty — paste or upload a file.")
    if len(text) > settings.MAX_RESUME_CHARS:
        raise HTTPException(status_code=422, detail="Resume exceeds character limit.")
    return text


@router.post("", response_model=CheckupResponse)
@limiter.limit("12/hour", key_func=rate_limit_key)
async def run_checkup(
    request: Request,
    jd_text: Annotated[str, Form(..., min_length=20)],
    job_title: Annotated[str, Form()] = "",
    resume_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> CheckupResponse:
    """Instant ATS-style checkup — no account or session required."""
    if len(jd_text) > settings.MAX_JD_CHARS:
        raise HTTPException(status_code=422, detail="Job description exceeds character limit.")

    raw_resume = await _extract_resume_text(resume_text=resume_text, file=file)
    jd_clean = jd_text.strip()
    cache_key = checkup_result_cache_key(resume_text=raw_resume, jd_text=jd_clean)
    cached = await load_cached_checkup_result(cache_key)
    if cached is not None:
        return CheckupResponse(result=cached)

    user_id = _optional_authenticated_user_id(authorization)
    if user_id:
        user = await db.get(User, user_id)
        if user is not None:
            try:
                await enforce_signed_in_checkup_quota(db, user=user)
            except ValueError as exc:
                if str(exc) == "checkup_period_limit":
                    raise HTTPException(
                        status_code=429,
                        detail="Checkup limit reached for this billing period.",
                    ) from exc
                raise
    else:
        client_ip = resolve_client_ip(request) or "unknown"
        user_agent = request.headers.get("user-agent", "")
        try:
            await enforce_anonymous_checkup_device_cap(
                user_agent=user_agent,
                client_ip=client_ip,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=429,
                detail="Daily checkup limit reached for this device. Try again tomorrow.",
            ) from exc

    accounting_user = str(user_id) if user_id else "anonymous"
    with llm_accounting_context(step="checkup", user_id=accounting_user):
        llm = get_llm_client_for_step("checkup")
        parsed = await _structure_resume(raw_resume, llm)
        result = await run_checkup_analysis(
            parsed=parsed,
            resume_text=raw_resume,
            jd_text=jd_clean,
            job_title=job_title.strip(),
            llm=llm,
            include_narrative=False,
        )
    await store_cached_checkup_result(cache_key, result)
    return CheckupResponse(result=result)
