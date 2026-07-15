"""Public resume checkup endpoint (M13 Step 42)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from slowapi.util import get_remote_address

from app.config import settings
from app.limiter import limiter
from app.llm.factory import get_llm_client
from app.models.qa import QAOutput
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.text_parser import extract_text_from_txt
from app.routers.resume import _structure_resume
from app.services.checkup_service import run_checkup_analysis

router = APIRouter(prefix="/api/checkup", tags=["checkup"])

ALLOWED_RESUME_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


class CheckupResponse(BaseModel):
    result: QAOutput


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
@limiter.limit("12/hour", key_func=get_remote_address)
async def run_checkup(
    request: Request,  # noqa: ARG001
    jd_text: Annotated[str, Form(..., min_length=20)],
    job_title: Annotated[str, Form()] = "",
    resume_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> CheckupResponse:
    """Instant ATS-style checkup — no account or session required."""
    if len(jd_text) > settings.MAX_JD_CHARS:
        raise HTTPException(status_code=422, detail="Job description exceeds character limit.")

    raw_resume = await _extract_resume_text(resume_text=resume_text, file=file)
    llm = get_llm_client(settings.LLM_PROVIDER, settings.LLM_MODEL, api_key=None)
    parsed = await _structure_resume(raw_resume, llm)
    result = await run_checkup_analysis(
        parsed=parsed,
        resume_text=raw_resume,
        jd_text=jd_text.strip(),
        job_title=job_title.strip(),
        llm=llm,
    )
    return CheckupResponse(result=result)
