from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import run_phase
from app.llm.factory import get_llm_client
from app.models.rewrite import ResumeVersion, TailoredResumeOutput
from app.models.session import PhaseStatus
from pydantic import BaseModel

from app.limiter import limiter
from app.services.session_store import get_session, reset_phase, update_session


def _cached_output_replayable(session, phase: int) -> bool:
    output = getattr(session, f"phase{phase}_output", None)
    if output is None:
        return False
    if phase == 1:
        return bool(output.must_have_keywords or output.nice_to_have_keywords)
    if phase == 2:
        return not (
            output.overall_score == 0
            and not (output.summary or "").strip()
            and not output.bullet_issues
            and not output.keyword_coverage.missing_must_have
        )
    return True

router = APIRouter(prefix="/api/sessions", tags=["phases"])


class RunPhaseRequest(BaseModel):
    force: bool = False


@router.post("/{session_id}/phases/{phase}/run", status_code=202)
@limiter.limit("10/minute")
async def trigger_phase(
    request: Request,
    session_id: str,
    phase: int,
    body: RunPhaseRequest = RunPhaseRequest(),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_model: str | None = Header(default=None, alias="X-Model"),
):
    if phase not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Phase must be 1, 2, 3, or 4.")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Pre-flight checks
    if phase >= 2 and getattr(session, f"phase{phase - 1}_status") != PhaseStatus.done:
        raise HTTPException(
            status_code=422,
            detail=f"Phase {phase - 1} must complete before starting Phase {phase}."
        )

    phase_status = getattr(session, f"phase{phase}_status")
    if phase_status == PhaseStatus.running:
        raise HTTPException(status_code=409, detail=f"Phase {phase} is already running.")

    # Persist BYOK choice to session so the SSE endpoint picks it up
    if x_provider and session.provider != x_provider:
        session.provider = x_provider
        await update_session(session)
    if x_model and session.model != x_model:
        session.model = x_model
        await update_session(session)
    if x_api_key:
        # Store the key temporarily in the session (cleared on expiry — never logged)
        session.byok_api_key = x_api_key

    if body.force:
        await reset_phase(session_id, phase)
        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    session.phase_run_requested = phase
    await update_session(session)

    return {
        "job_id": f"phase{phase}-{session_id[:8]}",
        "stream_url": f"/api/sessions/{session_id}/phases/{phase}/events",
    }


@router.get("/{session_id}/phases/{phase}/events")
async def phase_events(session_id: str, phase: int):
    """SSE stream. Triggers the phase and streams events to the client."""
    if phase not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Phase must be 1, 2, 3, or 4.")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    phase_status = getattr(session, f"phase{phase}_status")
    run_requested = session.phase_run_requested == phase

    # Replay cached output only when the phase finished, no fresh run was requested, and cache is usable.
    if phase_status == PhaseStatus.done and not run_requested and _cached_output_replayable(session, phase):
        output = getattr(session, f"phase{phase}_output")
        if output is not None:

            async def replay():
                payload = json.dumps({"event": "done", "phase": phase, "output": json.loads(output.model_dump_json())})
                yield f"data: {payload}\n\n"
                yield 'data: {"event": "stream_end"}\n\n'

            return StreamingResponse(replay(), media_type="text/event-stream")

    if run_requested:
        session.phase_run_requested = None
        await update_session(session)

    event_queue: asyncio.Queue = asyncio.Queue()
    # BYOK: use key stored at run-trigger time (never logged)
    llm = get_llm_client(session.provider, session.model, api_key=getattr(session, "byok_api_key", None))

    # Run the phase in the background
    task = asyncio.create_task(run_phase(session_id, phase, llm, event_queue))

    async def event_generator():
        sentinel = object()
        while True:
            try:
                item = await asyncio.wait_for(event_queue.get(), timeout=60)
            except asyncio.TimeoutError:
                yield "data: {\"event\": \"keepalive\"}\n\n"
                continue

            if item is sentinel:
                break

            yield f"data: {json.dumps(item)}\n\n"

            if item.get("event") in ("done", "error"):
                break

        # Signal end
        yield "data: {\"event\": \"stream_end\"}\n\n"

    async def run_and_signal():
        try:
            await task
        finally:
            await event_queue.put(object())  # sentinel

    asyncio.create_task(run_and_signal())
    return StreamingResponse(event_generator(), media_type="text/event-stream")


class TailoredPatchRequest(TailoredResumeOutput):
    pass


@router.patch("/{session_id}/resume/tailored")
async def patch_tailored_resume(session_id: str, body: dict):
    """Save user inline edits; creates a version snapshot."""
    import uuid
    from datetime import datetime, timezone

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.phase3_output:
        raise HTTPException(status_code=422, detail="No tailored resume exists yet.")

    # Apply the patch — simple field update on the section
    section = body.get("section")
    bullet_index = body.get("bullet_index")
    new_text = body.get("new_text", "")
    company = body.get("company")

    output = session.phase3_output
    if section == "summary":
        output.summary = new_text
    elif section == "experience" and company is not None and bullet_index is not None:
        for entry in output.experience:
            if entry.company == company and bullet_index < len(entry.bullets):
                entry.bullets[bullet_index] = new_text
                break
    elif section == "skills":
        output.skills = body.get("skills", output.skills)
    elif section == "education" and bullet_index is not None:
        institution = body.get("institution")
        for entry in output.education:
            if entry.institution == institution:
                bullets = list(entry.bullets)
                if bullet_index == len(bullets):
                    bullets.append(new_text)
                elif bullet_index < len(bullets):
                    if new_text.strip():
                        bullets[bullet_index] = new_text
                    else:
                        bullets.pop(bullet_index)
                entry.bullets = bullets
                break
    elif section == "education_bullets":
        institution = body.get("institution")
        for entry in output.education:
            if entry.institution == institution:
                entry.bullets = body.get("bullets", entry.bullets)
                break

    version_num = len(session.phase3_versions) + 1
    snapshot_id = str(uuid.uuid4())[:8]
    version = ResumeVersion(
        version=version_num,
        snapshot_id=snapshot_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        label=f"User edit: {section}",
        output=output,
    )
    session.phase3_versions.append(version)
    session.phase3_output = output
    await update_session(session)
    return {"version": version_num, "snapshot_id": snapshot_id}


@router.get("/{session_id}/resume/versions")
async def get_versions(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    versions = [
        {"version": v.version, "snapshot_id": v.snapshot_id, "created_at": v.created_at, "label": v.label}
        for v in session.phase3_versions
    ]
    return {"versions": versions}
