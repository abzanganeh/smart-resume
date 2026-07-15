"""Standalone resume checkup (M13 Step 42) — no tailoring session required."""

from __future__ import annotations

import structlog

from app.agent.phase1_keywords import _fallback_keyword_extraction
from app.agent.phase4_deterministic import build_blocking_issues_from_score, compute_score_result
from app.agent.phase4_narrative import synthesize_phase4_narrative
from app.agent.phase4_rank import compute_rank_label
from app.llm.base import LLMClient
from app.models.qa import QAOutput, ScoreAxis
from app.models.resume import ParsedResume
from app.models.rewrite import TailoredEducationEntry, TailoredExperienceEntry, TailoredResumeOutput

log = structlog.get_logger(__name__)


def parsed_to_tailored(parsed: ParsedResume) -> TailoredResumeOutput:
    return TailoredResumeOutput(
        contact=parsed.contact.model_dump(),
        summary=parsed.summary or "",
        skills=list(parsed.skills or []),
        experience=[
            TailoredExperienceEntry(
                title=e.title,
                company=e.company,
                dates=e.dates,
                bullets=list(e.bullets or []),
            )
            for e in parsed.experience
        ],
        projects=[p.model_dump() for p in parsed.projects],
        education=[
            TailoredEducationEntry(
                degree=e.degree,
                institution=e.institution,
                year=e.year or "",
                bullets=[],
            )
            for e in parsed.education
        ],
        certifications=list(parsed.certifications or []),
    )


async def run_checkup_analysis(
    *,
    parsed: ParsedResume,
    resume_text: str,
    jd_text: str,
    job_title: str,
    llm: LLMClient,
    career_stage: str = "mid",
) -> QAOutput:
    """Score + narrate a resume against a JD without a session."""
    tailored = parsed_to_tailored(parsed)
    phase1 = await _fallback_keyword_extraction(llm, jd_text, resume_text)
    must_have_terms = [k.term for k in phase1.must_have_keywords if k.term.strip()]

    score_result = compute_score_result(tailored, must_have_terms, career_stage=career_stage)
    blocking_issues = build_blocking_issues_from_score(score_result)
    quick_wins = [i for i in blocking_issues if i.impact == "high" and i.fix_effort == "one_click"]
    rank_label = compute_rank_label(score_result.ats_score)

    output = QAOutput(
        checklist=[],
        overall_status="warn" if score_result.ats_score < 70 else "pass",
        user_action_required=[],
        ats_score=score_result.ats_score,
        score_ceiling=score_result.score_ceiling,
        blocking_issues=blocking_issues,
        quick_wins=quick_wins,
        score_axes=[ScoreAxis(**axis.to_dict()) for axis in score_result.axes],
        missing_keywords=score_result.missing_keywords,
        single_section_keywords=score_result.single_section_keywords,
        rank_label=rank_label,
    )

    target_role = job_title.strip() or phase1.role_context.primary_domain.strip()
    try:
        narrative = await synthesize_phase4_narrative(
            llm=llm,
            score_result=score_result,
            target_role=target_role,
            rank_label=rank_label,
        )
        output = output.model_copy(
            update={
                "headline": narrative.headline,
                "category_summaries": [item.model_dump() for item in narrative.category_summaries],
            }
        )
    except Exception as exc:
        log.warning("checkup_narrative_failed", error=str(exc))

    return output
