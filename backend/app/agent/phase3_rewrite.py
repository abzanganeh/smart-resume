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
from app.agent.phase3_postprocess import (
    flatten_skill_terms,
    postprocess_tailored_output,
)
from app.models.rewrite import TailoredResumeOutput
from app.models.session import PhaseRunScope, Session
from app.services.company_intel import ensure_session_company_intel
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

_COMPANY_INTEL_INSTRUCTION = (
    "\n\nCOMPANY INTELLIGENCE — use these signals to align the summary and bullet "
    "phrasing with the employer's stated values where it is authentic.  Never "
    "fabricate alignment that is not supported by the candidate's actual experience."
)


# Snippet appended to the system prompt when retrieval has produced
# selected chunks.  Wording per SYSTEM_DESIGN_PHASE_2 §18.4 — the LLM
# composes *only* from the listed content and never invents new facts.
_RETRIEVAL_INSTRUCTION = (
    "\n\nAVAILABLE PROFILE CONTENT — compose the tailored resume from these "
    "chunks ONLY.  Do not invent companies, dates, metrics, or skills that "
    "are not present below.  Each chunk shows its relevance score against "
    "the job description so you can prioritize the highest-scoring ones."
)

_SCOPED_INSTRUCTION = (
    "\n\nSCOPED REGENERATION — regenerate ONLY the requested section or bullet. "
    "Return a JSON object containing ONLY the fields you are rewriting. "
    "Do not repeat unchanged sections.  Preserve all factual details."
)


def _merge_scoped_output(
    existing: TailoredResumeOutput,
    partial: TailoredResumeOutput,
    scope: PhaseRunScope,
) -> TailoredResumeOutput:
    """Merge a scoped LLM response into the existing tailored resume."""
    merged = existing.model_copy(deep=True)

    if scope.mode == "add" and scope.chunk_content:
        if scope.section == "experience" and partial.experience:
            merged.experience = [*merged.experience, *partial.experience]
        elif scope.section == "projects" and partial.projects:
            merged.projects = [*merged.projects, *partial.projects]
        elif scope.section == "education" and partial.education:
            merged.education = [*merged.education, *partial.education]
        elif scope.section == "skills" and partial.skills:
            # Existing skills may be categorized lines like "AI: Python, LLMs".
            # Dedupe against the FLATTENED individual terms, not the raw lines,
            # so we don't double-add a skill that's already inside a category.
            existing_terms = {t.lower() for t in flatten_skill_terms(merged.skills)}
            for raw_skill in partial.skills:
                for new_term in flatten_skill_terms([raw_skill]):
                    if new_term.lower() in existing_terms:
                        continue
                    merged.skills.append(new_term)
                    existing_terms.add(new_term.lower())
        elif scope.section == "summary" and partial.summary:
            merged.summary = partial.summary
        return merged

    if scope.section == "summary" and partial.summary:
        merged.summary = partial.summary
    elif scope.section == "skills" and partial.skills:
        merged.skills = partial.skills
    elif scope.section == "experience":
        if scope.bullet_index is not None and scope.company:
            new_bullet: str | None = None
            if partial.experience:
                entry = partial.experience[0]
                if entry.bullets:
                    new_bullet = entry.bullets[0]
            for exp in merged.experience:
                if exp.company == scope.company and new_bullet is not None:
                    if 0 <= scope.bullet_index < len(exp.bullets):
                        exp.bullets[scope.bullet_index] = new_bullet
                    break
        elif partial.experience:
            if scope.company:
                replaced = False
                for i, exp in enumerate(merged.experience):
                    if exp.company == scope.company:
                        merged.experience[i] = partial.experience[0]
                        replaced = True
                        break
                if not replaced:
                    merged.experience.append(partial.experience[0])
            else:
                merged.experience = partial.experience
    elif scope.section == "education" and partial.education:
        if scope.institution:
            for i, edu in enumerate(merged.education):
                if edu.institution == scope.institution:
                    merged.education[i] = partial.education[0]
                    break
        else:
            merged.education = partial.education
    elif scope.section == "projects" and partial.projects:
        merged.projects = partial.projects

    if partial.rewrite_notes:
        merged.rewrite_notes = [*merged.rewrite_notes, *partial.rewrite_notes]
    if partial.metrics_needed:
        merged.metrics_needed = partial.metrics_needed

    return merged


def _scoped_user_instruction(scope: PhaseRunScope, existing: TailoredResumeOutput) -> str:
    if scope.mode == "add" and scope.chunk_content:
        skills_clause = ""
        if scope.section == "skills":
            skills_clause = (
                " Return skills as 'Category Name: skill1, skill2' lines so they "
                "merge cleanly into the existing categorized skills."
            )
        return (
            f"ADD SECTION MODE — convert the following master-resume chunk into a "
            f"tailored ``{scope.section}`` section entry and return ONLY that section "
            f"in the JSON output.{skills_clause}\n\nCHUNK CONTENT:\n{scope.chunk_content}\n"
        )
    if scope.bullet_index is not None and scope.section == "experience":
        company = scope.company or ""
        current = ""
        for exp in existing.experience:
            if exp.company == company and scope.bullet_index < len(exp.bullets):
                current = exp.bullets[scope.bullet_index]
                break
        return (
            f"REGENERATE ONLY experience bullet index {scope.bullet_index} "
            f"for company \"{company}\".  Current bullet:\n{current}\n"
            f"Return JSON with a single experience entry whose bullets array "
            f"contains exactly one rewritten bullet."
        )
    if scope.company and scope.section == "experience":
        return (
            f"REGENERATE ONLY the experience entry for company \"{scope.company}\". "
            f"Return JSON with only the experience array containing that one entry."
        )
    if scope.institution and scope.section == "education":
        return (
            f"REGENERATE ONLY the education entry for institution "
            f"\"{scope.institution}\".  Return JSON with only the education array."
        )
    skills_format = ""
    if scope.section == "skills":
        skills_format = (
            " SKILLS FORMAT — each array entry MUST be a category string: "
            "\"Category Name: skill1, skill2, skill3\". "
            "Group into 3–5 categories ordered by JD relevance. "
            "Do NOT return plain individual skill strings."
        )
    return (
        f"REGENERATE ONLY the ``{scope.section}`` section.  "
        f"Return JSON containing only that section's field(s).{skills_format}"
    )


async def _resolve_chunk_content(scope: PhaseRunScope, user_id: str | None) -> PhaseRunScope:
    """Load master-resume chunk text when only ``chunk_id`` is provided."""
    if not scope.chunk_id or scope.chunk_content or not user_id:
        return scope
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return scope

    from sqlalchemy import select

    from app.db.engine import async_session_factory
    from app.models.master_resume import MasterResumeChunk

    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(MasterResumeChunk).where(
                    MasterResumeChunk.id == uuid.UUID(scope.chunk_id),
                    MasterResumeChunk.user_id == uid,
                )
            )
        ).scalar_one_or_none()
        await db.rollback()

    if row is None:
        return scope
    return scope.model_copy(update={"chunk_content": row.content})


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


async def _ensure_company_intel(session: Session) -> None:
    """Load company intel when the Phase 1 background task has not finished yet."""
    await ensure_session_company_intel(session)


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
    scope: PhaseRunScope | None = None,
) -> TailoredResumeOutput:
    scoped = scope is not None
    if scoped:
        await event_queue.put({
            "event": "progress",
            "phase": 3,
            "message": f"Regenerating {scope.section} section…",
        })
    else:
        await event_queue.put({"event": "progress", "phase": 3, "message": "Reading your resume and extracted JD keywords…"})

    if not session.phase1_output or not session.phase2_output:
        raise RuntimeError("Phases 1 and 2 must complete before Phase 3.")
    if scoped and not session.phase3_output:
        raise RuntimeError("Phase 3 must complete before a scoped regeneration.")

    await _ensure_company_intel(session)

    if scoped and scope is not None:
        scope = await _resolve_chunk_content(scope, session.user_id)

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
            retrieval_result = await _run_retrieval(user_uuid, jd_text)
            await event_queue.put({
                "event": "retrieval",
                "phase": 3,
                "data": retrieval_result.to_trace(),
            })

    # Estimate cost and surface it before the call.
    estimated_input = (len(resume_text) + len(jd_text)) // 3
    if retrieval_result is not None:
        estimated_input += retrieval_result.total_tokens
    if session.company_intel and not session.company_intel.is_empty():
        estimated_input += len(session.company_intel.render_for_prompt()) // 3
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
    # Fix 4 — inject user-supplied bullet corrections into the Phase 3 prompt.
    if session.bullet_fixes:
        fixes_block = "\n".join(
            f"  - Original: {bf.original}\n    Suggested fix: {bf.suggestion}"
            for bf in session.bullet_fixes
        )
        additions_section += (
            f"\nUSER-REQUESTED BULLET CORRECTIONS "
            f"(the candidate has rewritten these bullets from the audit — use these "
            f"corrected versions as the basis and polish them with JD keywords):\n{fixes_block}\n"
        )

    # Compose the system prompt — append extension blocks in priority order.
    system_content = _SYSTEM_BASE + "\n\n" + _PHASE3
    if scoped:
        system_content += _SCOPED_INSTRUCTION
    chunks_prompt_block = ""
    if retrieval_result is not None and retrieval_result.selected:
        system_content += _RETRIEVAL_INSTRUCTION
        chunks_prompt_block = (
            "\n\nAVAILABLE PROFILE CONTENT (retrieved from master resume):\n"
            f"{retrieval_result.render_for_prompt()}\n"
        )

    # Company intelligence block — prepended to user_content so the LLM
    # sees it before the JD.  Only injected when intel was successfully
    # fetched and contains at least one signal field.
    company_intel_block = ""
    if session.company_intel and not session.company_intel.is_empty():
        system_content += _COMPANY_INTEL_INSTRUCTION
        company_intel_block = (
            "COMPANY INTELLIGENCE:\n"
            f"{session.company_intel.render_for_prompt()}\n\n"
        )
        log.info(
            "phase3_company_intel_injected",
            company=session.company_intel.company_name,
            source=session.company_intel.source,
        )

    user_content = (
        f"CAREER STAGE: {career_stage}\n"
        f"TARGET ROLE: {target_role}\n"
        f"CAREER TRANSITION: {is_career_transition}\n"
        f"{company_intel_block}"
        f"{additions_section}"
        f"{chunks_prompt_block}\n"
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"EXTRACTED KEYWORDS (Phase 1):\n{session.phase1_output.model_dump_json()}\n\n"
        f"AUDIT RESULTS (Phase 2):\n{session.phase2_output.model_dump_json()}\n\n"
        f"ORIGINAL RESUME:\n{resume_text}"
    )

    if scoped and session.phase3_output:
        user_content += (
            f"\n\nCURRENT TAILORED RESUME (preserve all other sections):\n"
            f"{session.phase3_output.model_dump_json()}\n\n"
            f"{_scoped_user_instruction(scope, session.phase3_output)}"
        )
    elif not scoped and session.phase3_output:
        # Full re-run: pass the current tailored resume as the baseline so that
        # experience entries added from suggestions (not in the raw resume) are
        # preserved and built upon rather than silently dropped.
        user_content += (
            f"\n\nCURRENT TAILORED RESUME (baseline from previous run with user edits applied — "
            f"treat this as the starting point; preserve accepted experience entries and bullets "
            f"while applying all Phase 3 quality rules: bullet limits, skill categories, keyword placement):\n"
            f"{session.phase3_output.model_dump_json()}"
        )

    # Prompt budget gate (§6a "Determinism and prompt budget contract").
    # Raises ``PromptBudgetExceededError`` → orchestrator surfaces 422.
    assert_prompt_fits(system_content, user_content, model=llm.model_name)

    messages = [
        LLMMessage(role="system", content=system_content),
        LLMMessage(role="user", content=user_content),
    ]

    output = await complete_structured(llm, messages, TailoredResumeOutput, max_tokens=6000)

    if scoped and session.phase3_output:
        output = _merge_scoped_output(session.phase3_output, output, scope)
        # Preserve retrieval trace from the full run.
        prior = session.phase3_output
        if not output.selected_chunks and prior.selected_chunks:
            output.selected_chunks = prior.selected_chunks
        if not output.skipped_chunks and prior.skipped_chunks:
            output.skipped_chunks = prior.skipped_chunks
        if not output.retrieval_meta and prior.retrieval_meta:
            output.retrieval_meta = prior.retrieval_meta
    elif retrieval_result is not None:
        trace = retrieval_result.to_trace()
        output.selected_chunks = trace["selected_chunks"]
        output.skipped_chunks = trace["skipped_chunks"]
        output.retrieval_meta = trace["retrieval_meta"]

    must_have = (
        [k.term for k in session.phase1_output.must_have_keywords]
        if session.phase1_output
        else None
    )
    output = postprocess_tailored_output(output, must_have)

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
