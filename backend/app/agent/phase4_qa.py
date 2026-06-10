from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.agent.phase3_postprocess import flatten_skill_terms
from app.agent.phase4_score import compute_ats_score
from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.qa import BlockingIssue, QAOutput
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE4 = (Path(__file__).parent / "prompts" / "phase4.txt").read_text()


import re as _re

_HAS_NUMBER = _re.compile(r"\d")


def _filter_stale_metrics_needed(tailored) -> list:
    """Remove metrics_needed entries whose bullet has already been updated
    by the user to include a number/percentage.  Phase 4 should not
    auto-fail checklist #3 for bullets the user already quantified.
    """
    filtered = []
    exp_by_company = {e.company: e for e in (getattr(tailored, "experience", []) or [])}
    for entry in getattr(tailored, "metrics_needed", []) or []:
        company = entry.company if hasattr(entry, "company") else (entry.get("company") if isinstance(entry, dict) else None)
        idx = entry.bullet_index if hasattr(entry, "bullet_index") else (entry.get("bullet_index") if isinstance(entry, dict) else None)
        if company is None or idx is None:
            filtered.append(entry)
            continue
        exp = exp_by_company.get(company)
        if exp is None:
            # Company was removed from experience — entry is stale, skip it
            continue
        bullets = list(getattr(exp, "bullets", []) or [])
        if idx < len(bullets) and _HAS_NUMBER.search(bullets[idx]):
            # Bullet already contains a digit — user added a metric, entry is resolved
            continue
        filtered.append(entry)
    return filtered


def _collect_resume_text(tailored) -> str:
    """Concatenate every user-visible string in the tailored resume.

    Used by Phase 4 post-processing to detect whether a keyword the LLM
    flagged as "missing" actually appears anywhere — Skills, Summary,
    Experience bullets, Project descriptions, etc.
    """
    parts: list[str] = []
    if getattr(tailored, "summary", None):
        parts.append(tailored.summary)
    if getattr(tailored, "skills", None):
        parts.extend(tailored.skills)
    for entry in getattr(tailored, "experience", []) or []:
        for field in ("title", "company", "dates"):
            value = getattr(entry, field, "") or ""
            if value:
                parts.append(value)
        parts.extend(getattr(entry, "bullets", []) or [])
    for entry in getattr(tailored, "projects", []) or []:
        # Projects use a dict-like shape in TailoredResumeOutput; be defensive.
        if isinstance(entry, dict):
            for v in entry.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    parts.extend(s for s in v if isinstance(s, str))
        else:
            parts.append(str(entry))
    for entry in getattr(tailored, "education", []) or []:
        for field in ("degree", "institution", "year"):
            value = getattr(entry, field, "") or ""
            if value:
                parts.append(value)
        parts.extend(getattr(entry, "bullets", []) or [])
    for entry in getattr(tailored, "certifications", []) or []:
        if isinstance(entry, str):
            parts.append(entry)
        elif isinstance(entry, dict):
            parts.extend(str(v) for v in entry.values() if isinstance(v, (str, int)))
    return " \n ".join(p for p in parts if p)


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
    flat_skill_terms: list[str] = flatten_skill_terms(existing_skills)
    must_have_terms: list[str] = (
        [k.term for k in session.phase1_output.must_have_keywords]
        if session.phase1_output
        else []
    )

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE4),
        LLMMessage(
            role="user",
            content=(
                f"CAREER STAGE: {career_stage}\n"
                f"CAREER TRANSITION: {is_career_transition}\n\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"MUST-HAVE KEYWORDS:\n{json.dumps(must_have_terms)}\n\n"
                f"SKILLS ALREADY IN THE RESUME (categorized — do NOT suggest adding these to Skills again; suggest Experience/Summary instead):\n"
                f"{json.dumps(existing_skills)}\n\n"
                f"INDIVIDUAL SKILL TERMS (parsed from category lines for keyword coverage):\n"
                f"{', '.join(flat_skill_terms)}\n\n"
                f"TAILORED RESUME (Phase 3 output):\n{tailored.model_dump_json()}\n\n"
                f"UNRESOLVED METRICS NEEDED: {json.dumps([m.model_dump() if hasattr(m, 'model_dump') else m for m in _filter_stale_metrics_needed(tailored)])}"
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
        # QAOutput JSON can be 5-8 K tokens for a full resume; 8192 prevents
        # mid-string truncation on models with a 4096-token default output cap.
        max_tokens=8192,
        accept_result=lambda r: (
            "ats_score and score_ceiling must both be non-zero; "
            "provide an integer ATS compatibility score (0–100) for ats_score "
            "and the theoretical maximum for score_ceiling."
        )
        if r.ats_score == 0 and r.score_ceiling == 0
        else None,
    )
    # Post-process keyword guidance using the full tailored resume text
    # (not just the Skills list).  Two transformations:
    #   (a) Drop any keyword issue whose target term already appears
    #       anywhere in the resume — summary, skills, bullets, etc.
    #       This prevents the "still missing" persistence the user sees
    #       after editing a bullet to include the keyword.
    #   (b) For the remaining issues, if the keyword is already in
    #       Skills, rewrite the suggestion to point at Experience/Summary.
    full_text_corpus = _collect_resume_text(tailored).lower()

    def _extract_quoted_terms(text: str) -> list[str]:
        """Find any 'X', \"X\", or 'X' style phrases in the suggestion."""
        import re
        matches = re.findall(
            r"['\"\u2018\u2019\u201c\u201d]([^'\"\u2018\u2019\u201c\u201d]{2,80})['\"\u2018\u2019\u201c\u201d]",
            text,
        )
        return [m.strip() for m in matches if m.strip()]

    def _candidate_keywords(suggestion: str) -> list[str]:
        """Terms that the suggestion is likely advocating for.

        Uses both quoted phrases AND any Phase 1 must-have keyword whose
        verbatim form appears inside the suggestion text. This catches
        unquoted suggestions like "Add Python to the Skills section".
        """
        terms = _extract_quoted_terms(suggestion)
        lower = suggestion.lower()
        for term in must_have_terms:
            t = term.strip()
            if t and t.lower() in lower and t not in terms:
                terms.append(t)
        return terms

    def _skills_present(suggestion_lower: str) -> list[str]:
        return [t for t in flat_skill_terms if t.lower() in suggestion_lower]

    def _fix_suggestion(suggestion: str) -> str:
        lower = suggestion.lower()
        if not any(
            phrase in lower
            for phrase in ("skills section", "add to skills", "to the skills", "to skills")
        ):
            return suggestion
        already_present = _skills_present(lower)
        if not already_present:
            return suggestion
        kw_list = ", ".join(already_present)
        return (
            f"Reinforce {kw_list} in at least one Experience bullet or your Professional Summary — "
            f"{'it' if len(already_present) == 1 else 'they'} already appear in your Skills section."
        )

    corrected_issues = []
    for issue in output.blocking_issues:
        if issue.category == "keyword":
            candidates = _candidate_keywords(issue.suggestion)
            if candidates and all(c.lower() in full_text_corpus for c in candidates):
                log.info(
                    "phase4_keyword_issue_dropped",
                    suggestion=issue.suggestion[:120],
                    terms=candidates,
                )
                continue
            if existing_skills:
                fixed = _fix_suggestion(issue.suggestion)
                if fixed != issue.suggestion:
                    issue = issue.model_copy(update={"suggestion": fixed})
        corrected_issues.append(issue)
    # Inject deterministic findings that the LLM may have missed. The
    # engine produces 11 axes (keyword presence, dual placement, metrics,
    # action verbs, bullet length, resume length, weak phrases, first-person,
    # buzzwords, sections, contact). Each axis's issues become blocking
    # issues so the user sees every concrete gap and can ignore the ones
    # that don't apply.
    score_result = compute_ats_score(
        tailored, must_have_terms, career_stage=career_stage
    )

    flagged_terms = {
        term.lower()
        for issue in corrected_issues
        if issue.category == "keyword"
        for term in _candidate_keywords(issue.suggestion)
    }

    # Keyword issues — generated per-keyword so each one becomes its own
    # accept/ignore card in the UI rather than a single batched suggestion.
    for kw in score_result.missing_keywords:
        if kw.lower() in flagged_terms:
            continue
        corrected_issues.append(
            BlockingIssue(
                category="keyword",
                description=f"Missing must-have keyword: {kw}",
                suggestion=(
                    f"Add '{kw}' to the Skills section AND reinforce it in an Experience bullet "
                    "or your Professional Summary. If you don't have this skill, dismiss to ignore."
                ),
                impact="high",
                fix_effort="one_click",
            )
        )

    for kw in score_result.single_section_keywords:
        if kw.lower() in flagged_terms:
            continue
        sections = score_result.keyword_section_map.get(kw, [])
        section_label = sections[0] if sections else "skills"
        other_targets = [s for s in ("experience", "summary") if s != section_label]
        target_str = " or ".join(other_targets) if other_targets else "experience"
        corrected_issues.append(
            BlockingIssue(
                category="keyword",
                description=f"'{kw}' appears only in {section_label}",
                suggestion=(
                    f"Reinforce '{kw}' in your {target_str} so it appears in 2+ sections "
                    "(ATS keyword density rule)."
                ),
                impact="high",
                fix_effort="one_click",
            )
        )

    # Non-keyword axes — translate axis issues to blocking_issues with the
    # right category + impact mapping. Each axis already filters itself to
    # the top 5 offending bullets so we don't flood the UI.
    _axis_to_category = {
        "bullet_metrics": ("metric", "high", "user_input"),
        "action_verbs": ("bullet", "medium", "manual_rewrite"),
        "bullet_length": ("bullet", "medium", "manual_rewrite"),
        "resume_length": ("length", "medium", "manual_rewrite"),
        "weak_phrases": ("bullet", "high", "one_click"),
        "first_person": ("bullet", "high", "one_click"),
        "buzzwords": ("bullet", "medium", "manual_rewrite"),
        "section_completeness": ("section", "high", "user_input"),
        "contact_completeness": ("section", "high", "user_input"),
    }
    for axis in score_result.axes:
        if axis.status == "pass":
            continue
        mapping = _axis_to_category.get(axis.key)
        if mapping is None:
            continue
        category, impact, fix_effort = mapping
        for issue_text in axis.issues:
            corrected_issues.append(
                BlockingIssue(
                    category=category,
                    description=axis.label,
                    suggestion=issue_text,
                    impact=impact,
                    fix_effort=fix_effort,
                )
            )

    output = output.model_copy(update={"blocking_issues": corrected_issues})

    # Rebuild quick_wins from the corrected blocking_issues (strict subset rule).
    corrected_qw = [
        i for i in corrected_issues
        if i.impact == "high" and i.fix_effort == "one_click"
    ]
    output = output.model_copy(
        update={
            "quick_wins": corrected_qw,
            # Override the LLM-generated score with the deterministic one so
            # regenerating the same resume always yields the same number.
            "ats_score": score_result.ats_score,
            "score_ceiling": score_result.score_ceiling,
            "score_axes": [axis.to_dict() for axis in score_result.axes],
            "missing_keywords": score_result.missing_keywords,
            "single_section_keywords": score_result.single_section_keywords,
        }
    )

    await event_queue.put({"event": "partial", "phase": 4, "data": json.loads(output.model_dump_json())})
    log.info(
        "phase4_done",
        overall_status=output.overall_status,
        ats_score=output.ats_score,
        score_ceiling=output.score_ceiling,
        score_axes={a.key: round(a.score, 1) for a in score_result.axes},
        missing_keywords=score_result.missing_keywords,
        single_section_keywords=score_result.single_section_keywords,
        blocking=len(output.blocking_issues),
        actions=len(output.user_action_required),
    )
    return output
