from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog

from app.llm.base import LLMClient
from app.llm.pricing import estimate_cost, format_cost
from app.models.session import PhaseStatus, Session
from app.services import session_store
from app.services.retrieval.exceptions import (
    MasterResumeRequiredError,
    PromptBudgetExceededError,
)

log = structlog.get_logger()


async def run_phase(
    session_id: str,
    phase: int,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> None:
    """
    Run a single agent phase.
    Acquires the phase lock, executes the phase function, saves output, releases lock.
    Emits SSE events to event_queue throughout.
    """
    if not await session_store.acquire_phase_lock(session_id, phase):
        await event_queue.put({"event": "error", "phase": phase, "message": "Phase is already running."})
        raise RuntimeError(f"Phase {phase} is already running for session {session_id}")

    session = await session_store.get_session(session_id)
    if session is None:
        await event_queue.put({"event": "error", "phase": phase, "message": "Session not found."})
        await session_store.release_phase_lock(session_id, phase)
        return

    await session_store.update_phase_status(session_id, phase, PhaseStatus.running)
    await event_queue.put({"event": "progress", "phase": phase, "message": f"Phase {phase} starting…"})

    start = time.monotonic()
    try:
        from app.agent import phase1_keywords, phase2_audit, phase3_rewrite, phase4_qa

        match phase:
            case 1:
                output = await phase1_keywords.run(session, llm, event_queue)
            case 2:
                output = await phase2_audit.run(session, llm, event_queue)
            case 3:
                scope = session.phase_run_scope
                output = await phase3_rewrite.run(session, llm, event_queue, scope=scope)
            case 4:
                output = await phase4_qa.run(session, llm, event_queue)
            case _:
                raise ValueError(f"Unknown phase: {phase}")

        await session_store.save_phase_output(session_id, phase, output)

        # Clear stale markers after a successful phase run (§18.6).
        session = await session_store.get_session(session_id)
        if session is not None:
            if phase == 3:
                session.phase3_stale_since = None
                session.phase4_stale_since = None
                session.phase_run_scope = None
            elif phase == 4:
                session.phase4_stale_since = None
            await session_store.update_session(session)
        elapsed = round(time.monotonic() - start, 2)
        log.info("phase_complete", session_id=session_id, phase=phase, elapsed_s=elapsed,
                 provider=llm.provider_name, model=llm.model_name)
        await event_queue.put({
            "event": "done",
            "phase": phase,
            "output": json.loads(output.model_dump_json()),
        })

    except MasterResumeRequiredError as e:
        # IMPLEMENTATION_PLAN §6a — surface 409 so the frontend can route
        # the user to /profile.  Keep the phase status as ``pending`` so
        # they can rerun once a master resume has been uploaded.
        await session_store.update_phase_status(session_id, phase, PhaseStatus.pending)
        log.info("phase_blocked_master_resume_required", session_id=session_id, phase=phase)
        await event_queue.put({
            "event": "error",
            "phase": phase,
            "code": e.code,
            "status": 409,
            "message": str(e),
        })
        raise
    except PromptBudgetExceededError as e:
        await session_store.update_phase_status(session_id, phase, PhaseStatus.error)
        log.warning(
            "phase_prompt_budget_exceeded",
            session_id=session_id,
            phase=phase,
            total_tokens=e.total_tokens,
            budget=e.budget,
            model=e.model,
        )
        await event_queue.put({
            "event": "error",
            "phase": phase,
            "code": e.code,
            "status": 422,
            "message": str(e),
            "total_tokens": e.total_tokens,
            "budget": e.budget,
            "model": e.model,
        })
        raise
    except Exception as e:
        await session_store.update_phase_status(session_id, phase, PhaseStatus.error)
        log.error("phase_error", session_id=session_id, phase=phase, error=str(e))
        await event_queue.put({"event": "error", "phase": phase, "message": str(e)})
        raise
    finally:
        await session_store.release_phase_lock(session_id, phase)
