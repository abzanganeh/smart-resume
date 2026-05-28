from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.audit import AuditOutput
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE2 = (Path(__file__).parent / "prompts" / "phase2.txt").read_text()


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> AuditOutput:
    await event_queue.put({"event": "progress", "phase": 2, "message": "Auditing resume against job description…"})

    if not session.phase1_output:
        raise RuntimeError("Phase 1 must complete before Phase 2.")

    resume_text = session.resume_raw or ""
    jd_text = session.jd_raw or ""
    keywords_json = session.phase1_output.model_dump_json()
    career_stage = session.user_info.career_stage if session.user_info else "senior"

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE2),
        LLMMessage(
            role="user",
            content=(
                f"CAREER STAGE: {career_stage}\n\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"EXTRACTED KEYWORDS (Phase 1 output):\n{keywords_json}\n\n"
                f"CANDIDATE'S RESUME:\n{resume_text}"
            ),
        ),
    ]

    output = await complete_structured(llm, messages, AuditOutput)
    await event_queue.put({"event": "partial", "phase": 2, "data": json.loads(output.model_dump_json())})
    log.info("phase2_done", overall_score=output.overall_score, issues=len(output.bullet_issues))
    return output
