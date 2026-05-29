from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.pricing import estimate_cost, format_cost
from app.llm.structured import complete_structured
from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE3 = (Path(__file__).parent / "prompts" / "phase3.txt").read_text()


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> TailoredResumeOutput:
    await event_queue.put({"event": "progress", "phase": 3, "message": "Reading your resume and extracted JD keywords…"})

    if not session.phase1_output or not session.phase2_output:
        raise RuntimeError("Phases 1 and 2 must complete before Phase 3.")

    resume_text = session.resume_raw or ""
    jd_text = session.jd_raw or ""
    user_info = session.user_info
    career_stage = user_info.career_stage if user_info else "mid"
    target_role = user_info.target_role if user_info else ""
    is_career_transition = user_info.is_career_transition if user_info else False

    # Estimate cost and surface it before the call
    estimated_input = (len(resume_text) + len(jd_text)) // 3
    estimated_output = 2000
    cost = estimate_cost(estimated_input, estimated_output, llm.provider_name, llm.model_name)
    await event_queue.put({
        "event": "cost_estimate",
        "phase": 3,
        "cost": cost,
        "cost_formatted": format_cost(cost),
        "provider": llm.provider_name,
        "model": llm.model_name,
    })

    await event_queue.put({"event": "progress", "phase": 3, "message": "Analyzing which experience bullets match the JD requirements…"})
    await asyncio.sleep(0)   # yield to event loop so the message is flushed
    await event_queue.put({"event": "progress", "phase": 3, "message": "Rewriting bullets with strong action verbs and exact JD phrasing…"})

    # User-declared additions (skills/keywords they have but weren't in the resume)
    additions_section = ""
    if session.user_claimed_keywords:
        kw_list = ", ".join(session.user_claimed_keywords)
        additions_section += (
            f"\nUSER-DECLARED SKILLS/KEYWORDS (the candidate confirmed they have these "
            f"but they were missing from the original resume — incorporate them naturally):\n{kw_list}\n"
        )
    if session.user_extra_notes.strip():
        additions_section += (
            f"\nADDITIONAL CONTEXT FROM CANDIDATE:\n{session.user_extra_notes.strip()}\n"
        )

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE3),
        LLMMessage(
            role="user",
            content=(
                f"CAREER STAGE: {career_stage}\n"
                f"TARGET ROLE: {target_role}\n"
                f"CAREER TRANSITION: {is_career_transition}\n"
                f"{additions_section}\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"EXTRACTED KEYWORDS (Phase 1):\n{session.phase1_output.model_dump_json()}\n\n"
                f"AUDIT RESULTS (Phase 2):\n{session.phase2_output.model_dump_json()}\n\n"
                f"ORIGINAL RESUME:\n{resume_text}"
            ),
        ),
    ]

    output = await complete_structured(llm, messages, TailoredResumeOutput, max_tokens=6000)
    await event_queue.put({"event": "partial", "phase": 3, "data": json.loads(output.model_dump_json())})
    log.info("phase3_done", metrics_needed=len(output.metrics_needed), notes=len(output.rewrite_notes))
    return output
