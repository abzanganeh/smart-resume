from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import cover_letter as cover_letter_agent
from app.db.engine import get_db
from app.llm.factory import get_llm_client_for_step
from app.llm.token_accounting import llm_accounting_context
from app.limiter import limiter
from app.models.cover_letter import CoverLetterTone
from app.services.billing.exceptions import (
    AccountSuspendedError,
    CreditsLockedUntilVerificationError,
    FreeTierAiBudgetExceededError,
    InsufficientCreditsError,
    free_tier_ai_cap_detail,
)
from app.services.session_ownership import require_session_user
from app.services.billing.credit_spend import credits_locked_detail
from app.services.billing.exhaustion_paywall import insufficient_credits_detail
from app.services.billing.quota import check_quota_for_cover_letter
from app.services.export_service import (
    render_cover_letter_docx,
    render_cover_letter_pdf,
    render_cover_letter_txt,
)
from app.services.llm.plan_code_for_llm import resolve_plan_code_for_llm
from app.services.session_store import get_session, update_session

router = APIRouter(prefix="/api/sessions", tags=["cover-letter"])
log = structlog.get_logger("cover_letter.router")

_cover_letter_locks: set[str] = set()


class CoverLetterGenerateRequest(BaseModel):
    tone: CoverLetterTone = "balanced"
    custom_hook: str | None = Field(default=None, max_length=500)


def _require_tailored_resume(session) -> None:
    if not session.phase3_output:
        raise HTTPException(status_code=409, detail={"code": "resume_required"})


@router.get("/{session_id}/cover-letter")
@limiter.limit("60/minute")
async def get_cover_letter(request: Request, session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.cover_letter_output:
        raise HTTPException(status_code=404, detail="No cover letter generated yet.")
    return json.loads(session.cover_letter_output.model_dump_json())


@router.post("/{session_id}/cover-letter")
@limiter.limit("10/minute")
async def generate_cover_letter(
    request: Request,
    session_id: str,
    body: CoverLetterGenerateRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Generate a cover letter and stream progress via SSE."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_tailored_resume(session)

    if session_id in _cover_letter_locks:
        raise HTTPException(status_code=409, detail="Cover letter generation is already running.")

    try:
        user = await require_session_user(authorization, session, db)
        await check_quota_for_cover_letter(db, user=user, session_id=session_id)
    except AccountSuspendedError:
        raise HTTPException(status_code=403, detail={"code": "account_suspended"})
    except CreditsLockedUntilVerificationError as exc:
        raise HTTPException(
            status_code=403,
            detail=credits_locked_detail(balance=exc.balance),
        ) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail=await insufficient_credits_detail(
                db,
                user=user,
                exc=exc,
                message="You're out of credits. Cover letter generation costs 1 credit.",
            ),
        ) from exc

    plan_code = await resolve_plan_code_for_llm(db, user)
    llm = get_llm_client_for_step("cover_letter", plan_code=plan_code)

    async def event_generator():
        _cover_letter_locks.add(session_id)
        event_queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def run_and_signal():
            try:
                refreshed = await get_session(session_id)
                if refreshed is None:
                    await event_queue.put({
                        "event": "error",
                        "message": "Session not found.",
                    })
                    return
                with llm_accounting_context(
                    session_id,
                    "cover_letter",
                    user_id=str(user.id),
                ):
                    output = await cover_letter_agent.run(
                        refreshed,
                        llm,
                        event_queue,
                        tone=body.tone,
                        custom_hook=body.custom_hook,
                    )
                session_after = await get_session(session_id)
                if session_after is not None:
                    session_after.cover_letter_output = output
                    await update_session(session_after)
                await db.commit()
                await event_queue.put({
                    "event": "done",
                    "output": json.loads(output.model_dump_json()),
                })
            except FreeTierAiBudgetExceededError:
                await db.rollback()
                await event_queue.put({
                    "event": "error",
                    **free_tier_ai_cap_detail(),
                    "status": 402,
                })
            except Exception as exc:
                await db.rollback()
                log.exception("cover_letter_generation_failed", session_id=session_id, error=str(exc))
                await event_queue.put({
                    "event": "error",
                    "message": "Cover letter generation failed. Please retry.",
                })
            finally:
                await event_queue.put(sentinel)

        task = asyncio.create_task(run_and_signal())

        try:
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=60)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'event': 'keepalive'})}\n\n"
                    continue

                if item is sentinel:
                    break

                yield f"data: {json.dumps(item)}\n\n"

                if item.get("event") in ("done", "error"):
                    break

            yield f"data: {json.dumps({'event': 'stream_end'})}\n\n"
            await task
        finally:
            _cover_letter_locks.discard(session_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{session_id}/cover-letter/export")
@limiter.limit("60/minute")
async def export_cover_letter(
    request: Request,
    session_id: str,
    format: str = "pdf",
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.cover_letter_output:
        raise HTTPException(status_code=422, detail="No cover letter to export yet.")

    if format == "pdf":
        content = await render_cover_letter_pdf(session)
        media_type = "application/pdf"
        filename = "cover_letter.pdf"
    elif format == "docx":
        content = render_cover_letter_docx(session)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "cover_letter.docx"
    elif format == "txt":
        content = render_cover_letter_txt(session).encode()
        media_type = "text/plain"
        filename = "cover_letter.txt"
    else:
        raise HTTPException(status_code=400, detail="format must be pdf, docx, or txt")

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
