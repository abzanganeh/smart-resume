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
                output = await phase3_rewrite.run(session, llm, event_queue)
            case 4:
                output = await phase4_qa.run(session, llm, event_queue)
            case _:
                raise ValueError(f"Unknown phase: {phase}")

        await session_store.save_phase_output(session_id, phase, output)
        elapsed = round(time.monotonic() - start, 2)
        log.info("phase_complete", session_id=session_id, phase=phase, elapsed_s=elapsed,
                 provider=llm.provider_name, model=llm.model_name)
        await event_queue.put({
            "event": "done",
            "phase": phase,
            "output": json.loads(output.model_dump_json()),
        })

    except Exception as e:
        await session_store.update_phase_status(session_id, phase, PhaseStatus.error)
        log.error("phase_error", session_id=session_id, phase=phase, error=str(e))
        await event_queue.put({"event": "error", "phase": phase, "message": str(e)})
        raise
    finally:
        await session_store.release_phase_lock(session_id, phase)
