from __future__ import annotations

from fastapi import APIRouter

from app.services.session_store import create_session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201)
async def new_session():
    session = await create_session()
    return {"session_id": session.session_id}
