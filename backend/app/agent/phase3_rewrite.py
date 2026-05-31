from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import structlog

from app.db.engine import async_session_factory
from app.llm.base import LLMClient, LLMMessage
from app.llm.pricing import estimate_cost, format_cost
from app.llm.structured import complete_structured
from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session
from app.services.retrieval.exceptions import (
    MasterResumeRequiredError,
    PromptBudgetExceededError,
)
from app.services.retrieval.retrieval_service import (
    RetrievalResult,
    assert_prompt_fits,
    retrieve_for_jd,
)

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE3 = (Path(__file__).parent / "prompts" / "phase3.txt").read_text()


# Snippet appended to the system prompt when retrieval has produced
# selected chunks.  Wording per SYSTEM_DESIGN_PHASE_2 §18.4 — the LLM
# composes *only* from the listed content and never invents new facts.
_RETRIEVAL_INSTRUCTION = (
    "\n\nAVAILABLE PROFILE CONTENT — compose the tailored resume from these "
    "chunks ONLY.  Do not invent companies, dates, metrics, or skills that "
    "are not present below.  Each chunk shows its relevance score against "
    "the job description so you can prioritize the highest-scoring ones."
)


async def _run_retrieval(
    user_id: uuid.UUID, jd_text: str
) -> RetrievalResult:
    """Open a short-lived DB session to query the retrieval surface."""
    async with async_session_factory() as db:
        try:
            return await retrieve_for_jd(db, user_id=user_id, jd_text=jd_text)
        finally:
            # Read-only — explicit rollback so the connection returns
            # to the pool without an implicit commit.
            await db.rollback()


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

    # -------------------------------------------------------------------
    # Master-resume retrieval (IMPLEMENTATION_PLAN §6a / Step 10).
    #
    # When the session is bound to an authenticated user, pull the
    # relevant chunks before the LLM call.  Anonymous demo sessions
    # (``user_id`` is None) keep the legacy "raw resume only" behaviour
    # so the existing flow continues to work — Step 8/9 makes uploading
    # the master resume the canonical onboarding path.
    # -------------------------------------------------------------------
    retrieval_result: RetrievalResult | None = None
    if session.user_id:
        try:
            user_uuid = uuid.UUID(session.user_id)
        except ValueError:
            user_uuid = None
        if user_uuid is not None:
            await event_queue.put({
                "event": "progress",
                "phase": 3,
                "message": "Selecting relevant master-resume chunks against this JD…",
            })
            try:
                retrieval_result = await _run_retrieval(user_uuid, jd_text)
            except MasterResumeRequiredError:
                # Propagate the structured 409 up the orchestrator —
                # ``app/agent/orchestrator.py`` catches it and turns the
                # SSE error event into ``{"code": "master_resume_required"}``
                # so the frontend can route to ``/profile``.
                raise
            else:
                await event_queue.put({
                    "event": "retrieval",
                    "phase": 3,
                    "data": retrieval_result.to_trace(),
                })

    # Estimate cost and surface it before the call.
    estimated_input = (len(resume_text) + len(jd_text)) // 3
    if retrieval_result is not None:
        estimated_input += retrieval_result.total_tokens
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

    # User-declared additions (skills/keywords they have but weren't in the resume).
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

    # Compose the system prompt — append the retrieval instructions when
    # we have chunks to pin the LLM against.
    system_content = _SYSTEM_BASE + "\n\n" + _PHASE3
    chunks_prompt_block = ""
    if retrieval_result is not None and retrieval_result.selected:
        system_content += _RETRIEVAL_INSTRUCTION
        chunks_prompt_block = (
            "\n\nAVAILABLE PROFILE CONTENT (retrieved from master resume):\n"
            f"{retrieval_result.render_for_prompt()}\n"
        )

    user_content = (
        f"CAREER STAGE: {career_stage}\n"
        f"TARGET ROLE: {target_role}\n"
        f"CAREER TRANSITION: {is_career_transition}\n"
        f"{additions_section}"
        f"{chunks_prompt_block}\n"
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"EXTRACTED KEYWORDS (Phase 1):\n{session.phase1_output.model_dump_json()}\n\n"
        f"AUDIT RESULTS (Phase 2):\n{session.phase2_output.model_dump_json()}\n\n"
        f"ORIGINAL RESUME:\n{resume_text}"
    )

    # Prompt budget gate (§6a "Determinism and prompt budget contract").
    # Raises ``PromptBudgetExceededError`` → orchestrator surfaces 422.
    assert_prompt_fits(system_content, user_content, model=llm.model_name)

    messages = [
        LLMMessage(role="system", content=system_content),
        LLMMessage(role="user", content=user_content),
    ]

    output = await complete_structured(llm, messages, TailoredResumeOutput, max_tokens=6000)

    # Attach retrieval transparency so the UI / version snapshots can
    # render "selected vs skipped" panels even after a page reload.
    if retrieval_result is not None:
        trace = retrieval_result.to_trace()
        output.selected_chunks = trace["selected_chunks"]
        output.skipped_chunks = trace["skipped_chunks"]
        output.retrieval_meta = trace["retrieval_meta"]

    await event_queue.put({"event": "partial", "phase": 3, "data": json.loads(output.model_dump_json())})
    log.info(
        "phase3_done",
        metrics_needed=len(output.metrics_needed),
        notes=len(output.rewrite_notes),
        selected_chunks=len(output.selected_chunks),
        skipped_chunks=len(output.skipped_chunks),
    )
    return output


__all__ = [
    "MasterResumeRequiredError",
    "PromptBudgetExceededError",
    "run",
]
