"""Deterministic Phase 4 score + blocking-issue injection (shared by session QA and checkup)."""

from __future__ import annotations

from app.agent.phase4_score import ResumeQualityResult, compute_ats_score
from app.agent.tone_profile import JDToneProfile
from app.models.qa import BlockingIssue, IssueAnchor

_AXIS_TO_CATEGORY: dict[str, tuple[str, str, str]] = {
    "tone_alignment": ("bullet", "medium", "manual_rewrite"),
    "bullet_metrics": ("metric", "high", "user_input"),
    "action_verbs": ("bullet", "medium", "manual_rewrite"),
    "bullet_length": ("bullet", "medium", "manual_rewrite"),
    "resume_length": ("length", "medium", "manual_rewrite"),
    "weak_phrases": ("bullet", "high", "one_click"),
    "first_person": ("bullet", "high", "one_click"),
    "buzzwords": ("bullet", "medium", "manual_rewrite"),
    "section_completeness": ("section", "high", "user_input"),
    "contact_completeness": ("section", "high", "user_input"),
    "field_completeness": ("section", "high", "user_input"),
}


def issue_anchor_from_dict(anchor: dict[str, int | str] | None) -> IssueAnchor | None:
    if not anchor:
        return None
    section = anchor.get("section")
    entry_index = anchor.get("entry_index")
    if section not in ("experience", "projects", "education") or entry_index is None:
        return None
    bullet_index = anchor.get("bullet_index")
    return IssueAnchor(
        section=section,  # type: ignore[arg-type]
        entry_index=int(entry_index),
        bullet_index=int(bullet_index) if bullet_index is not None else None,
    )


def compute_score_result(
    tailored,
    must_have_terms: list[str],
    *,
    career_stage: str = "mid",
    tone_profile: JDToneProfile | None = None,
) -> ResumeQualityResult:
    keywords = [k for k in must_have_terms if k and k.strip()]
    return compute_ats_score(
        tailored,
        keywords,
        career_stage=career_stage,
        tone_profile=tone_profile,
    )


def build_blocking_issues_from_score(
    score_result: ResumeQualityResult,
    *,
    existing_issues: list[BlockingIssue] | None = None,
    flagged_keyword_terms: set[str] | None = None,
) -> list[BlockingIssue]:
    """Turn deterministic axis findings into blocking issues."""
    corrected_issues = list(existing_issues or [])
    flagged_terms = flagged_keyword_terms or set()

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

    for axis in score_result.axes:
        if axis.status == "pass":
            continue
        mapping = _AXIS_TO_CATEGORY.get(axis.key)
        if mapping is None:
            continue
        category, impact, fix_effort = mapping
        if axis.anchored_issues:
            for anchored in axis.anchored_issues:
                corrected_issues.append(
                    BlockingIssue(
                        category=category,  # type: ignore[arg-type]
                        description=axis.label,
                        suggestion=anchored.text,
                        impact=impact,  # type: ignore[arg-type]
                        fix_effort=fix_effort,  # type: ignore[arg-type]
                        anchor=issue_anchor_from_dict(anchored.anchor),
                    )
                )
            continue
        for issue_text in axis.issues:
            corrected_issues.append(
                BlockingIssue(
                    category=category,  # type: ignore[arg-type]
                    description=axis.label,
                    suggestion=issue_text,
                    impact=impact,  # type: ignore[arg-type]
                    fix_effort=fix_effort,  # type: ignore[arg-type]
                )
            )

    return corrected_issues
