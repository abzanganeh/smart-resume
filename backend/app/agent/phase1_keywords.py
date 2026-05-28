from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.context import truncate_to_fit
from app.llm.structured import complete_structured
from app.models.keywords import KeywordExtractionOutput
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE1 = (Path(__file__).parent / "prompts" / "phase1.txt").read_text()


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> KeywordExtractionOutput:
    await event_queue.put({"event": "progress", "phase": 1, "message": "Analyzing job description…"})

    resume_text = session.resume_raw or ""
    jd_text = session.jd_raw or ""
    resume_text, jd_text = truncate_to_fit(llm, resume_text, jd_text)

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE1),
        LLMMessage(
            role="user",
            content=(
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"CANDIDATE'S CURRENT RESUME (for keyword presence check):\n{resume_text}"
            ),
        ),
    ]

    await event_queue.put({"event": "progress", "phase": 1, "message": "Extracting must-have keywords…"})
    output = await complete_structured(llm, messages, KeywordExtractionOutput)

    # Mark which keywords are already present in the resume
    resume_lower = resume_text.lower()
    for kw in output.must_have_keywords + output.nice_to_have_keywords:
        kw.present_in_resume = kw.term.lower() in resume_lower

    await event_queue.put({"event": "partial", "phase": 1, "data": json.loads(output.model_dump_json())})
    log.info("phase1_done", must_have=len(output.must_have_keywords), nice_to_have=len(output.nice_to_have_keywords))
    return output
