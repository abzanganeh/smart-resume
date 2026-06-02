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

    existing_skills: list[str] = tailored.skills or []

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE4),
        LLMMessage(
            role="user",
            content=(
                f"CAREER STAGE: {career_stage}\n"
                f"CAREER TRANSITION: {is_career_transition}\n\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"MUST-HAVE KEYWORDS:\n{json.dumps([k.term for k in session.phase1_output.must_have_keywords] if session.phase1_output else [])}\n\n"
                f"SKILLS ALREADY IN THE RESUME (do NOT suggest adding these to Skills — suggest Experience/Summary instead):\n"
                f"{', '.join(existing_skills)}\n\n"
                f"TAILORED RESUME (Phase 3 output):\n{tailored.model_dump_json()}\n\n"
                f"UNRESOLVED METRICS NEEDED: {json.dumps([m.model_dump() for m in tailored.metrics_needed])}"
            ),
        ),
    ]

    # Reject responses where both ats_score and score_ceiling are 0 — this
    # indicates the model omitted these fields (Pydantic default=0) rather
    # than genuinely computing them. Force a retry so the model provides
    # real values. A legitimate ats_score=0 would still have score_ceiling>0.
    output = await complete_structured(
        llm,
        messages,
        QAOutput,
        accept_result=lambda r: (
            "ats_score and score_ceiling must both be non-zero; "
            "provide an integer ATS compatibility score (0–100) for ats_score "
            "and the theoretical maximum for score_ceiling."
        )
        if r.ats_score == 0 and r.score_ceiling == 0
        else None,
    )
    # Post-process: if the LLM suggested adding a skill that is already in the
    # Skills section, correct the suggestion to point to Experience or Summary.
    if existing_skills:
        skills_lower = {s.lower() for s in existing_skills}

        def _fix_suggestion(suggestion: str) -> str:
            """Replace 'Add X to Skills' with 'Reinforce X in Experience/Summary' when X is already in Skills."""
            lower = suggestion.lower()
            # Detect the common pattern the LLM emits
            if "skills section" in lower or "add to skills" in lower or "to the skills" in lower:
                already_present = [s for s in existing_skills if s.lower() in lower]
                if already_present:
                    kw_list = ", ".join(already_present)
                    return (
                        f"Reinforce {kw_list} in at least one Experience bullet or your Professional Summary — "
                        f"{'it' if len(already_present) == 1 else 'they'} already appear in your Skills section."
                    )
            return suggestion

        corrected_issues = []
        for issue in output.blocking_issues:
            if issue.category == "keyword":
                fixed = _fix_suggestion(issue.suggestion)
                if fixed != issue.suggestion:
                    issue = issue.model_copy(update={"suggestion": fixed})
            corrected_issues.append(issue)
        output = output.model_copy(update={"blocking_issues": corrected_issues})

        # Rebuild quick_wins from the corrected blocking_issues (strict subset rule)
        corrected_qw = [
            i for i in corrected_issues
            if i.impact == "high" and i.fix_effort == "one_click"
        ]
        output = output.model_copy(update={"quick_wins": corrected_qw})

    await event_queue.put({"event": "partial", "phase": 4, "data": json.loads(output.model_dump_json())})
    log.info(
        "phase4_done",
        overall_status=output.overall_status,
        ats_score=output.ats_score,
        blocking=len(output.blocking_issues),
        actions=len(output.user_action_required),
    )
    return output
