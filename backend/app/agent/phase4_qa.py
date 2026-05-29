from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.qa import QAOutput
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE4 = (Path(__file__).parent / "prompts" / "phase4.txt").read_text()


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> QAOutput:
    await event_queue.put({"event": "progress", "phase": 4, "message": "Running quality assurance checklist…"})

    if not session.phase3_output:
        raise RuntimeError("Phase 3 must complete before Phase 4.")

    user_info = session.user_info
    career_stage = user_info.career_stage if user_info else "mid"
    is_career_transition = user_info.is_career_transition if user_info else False
    jd_text = session.jd_raw or ""
    tailored = session.phase3_output

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE4),
        LLMMessage(
            role="user",
            content=(
                f"CAREER STAGE: {career_stage}\n"
                f"CAREER TRANSITION: {is_career_transition}\n\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"MUST-HAVE KEYWORDS:\n{json.dumps([k.term for k in session.phase1_output.must_have_keywords] if session.phase1_output else [])}\n\n"
                f"TAILORED RESUME (Phase 3 output):\n{tailored.model_dump_json()}\n\n"
                f"UNRESOLVED METRICS NEEDED: {json.dumps([m.model_dump() for m in tailored.metrics_needed])}"
            ),
        ),
    ]

    output = await complete_structured(llm, messages, QAOutput)
    await event_queue.put({"event": "partial", "phase": 4, "data": json.loads(output.model_dump_json())})
    log.info("phase4_done", overall_status=output.overall_status, actions=len(output.user_action_required))
    return output
