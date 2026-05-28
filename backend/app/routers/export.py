from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.export_service import render_docx, render_pdf, render_txt
from app.services.session_store import get_session

router = APIRouter(prefix="/api/sessions", tags=["export"])


@router.get("/{session_id}/export")
async def export_resume(session_id: str, format: str = "pdf"):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.phase3_output:
        raise HTTPException(status_code=422, detail="No tailored resume to export yet. Complete Phase 3 first.")

    if format == "pdf":
        content = await render_pdf(session)
        media_type = "application/pdf"
        filename = "tailored_resume.pdf"
    elif format == "docx":
        content = render_docx(session)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "tailored_resume.docx"
    elif format == "txt":
        content = render_txt(session).encode()
        media_type = "text/plain"
        filename = "tailored_resume.txt"
    else:
        raise HTTPException(status_code=400, detail="format must be pdf, docx, or txt")

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
