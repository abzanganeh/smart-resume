from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.rewrite import TailoredResumeOutput
from app.services.session_store import create_session, get_session, update_session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201)
async def new_session():
    session = await create_session()
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
    return {
        "session_id": session.session_id,
        "ok": True,
        "resume_raw": session.resume_raw or "",
        "phases": phases_out,
    }


class TailoredEditRequest(BaseModel):
    tailored_output: dict


@router.patch("/{session_id}/tailored")
async def save_tailored_edits(session_id: str, body: TailoredEditRequest):
    """Persist user-edited tailored resume (overwrites phase3_output)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        session.phase3_output = TailoredResumeOutput.model_validate(body.tailored_output)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid tailored output: {exc}")
    await update_session(session)
    return {"ok": True}
