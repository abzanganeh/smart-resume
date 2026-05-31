from __future__ import annotations

import asyncio
import json
from pathlib import Path

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.fit import FitAnalysisOutput
from app.services.retrieval.retrieval_service import RetrievalResult, retrieve_for_jd

log = structlog.get_logger("job_fit")

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_JOB_FIT = (Path(__file__).parent / "prompts" / "job_fit.txt").read_text()

# Standard tier default per SYSTEM_DESIGN_PHASE_2 §18.9
FIT_LLM_PROVIDER = "gemini"
FIT_LLM_MODEL = "gemini-2.5-flash-lite"


async def run(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    jd_text: str,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> FitAnalysisOutput:
    await event_queue.put({
        "event": "progress",
        "message": "Matching master resume to job description…",
    })

    retrieval: RetrievalResult = await retrieve_for_jd(
        db, user_id=user_id, jd_text=jd_text
    )

    await event_queue.put({
        "event": "progress",
        "message": "Analyzing fit with AI…",
    })

    chunk_block = retrieval.render_for_prompt()
    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _JOB_FIT),
        LLMMessage(
            role="user",
            content=(
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"MASTER RESUME CHUNKS (retrieved by vector similarity):\n"
                f"{chunk_block or '(no chunks above threshold — analyze gaps honestly)'}\n\n"
                f"RETRIEVAL META:\n{json.dumps(retrieval.meta, indent=2)}"
            ),
        ),
    ]

    output = await complete_structured(llm, messages, FitAnalysisOutput, max_tokens=3000)

    await event_queue.put({
        "event": "partial",
        "data": json.loads(output.model_dump_json()),
    })
    log.info(
        "job_fit_done",
        overall_fit_score=output.overall_fit_score,
        fit_label=output.fit_label,
        sections=len(output.section_fits),
    )
    return output
