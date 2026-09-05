"""Deterministic checkup guidance — no LLM."""

from __future__ import annotations

from app.agent.phase4_score import ResumeQualityResult
from app.models.qa import BlockingIssue, CheckupGuidance, TailorVerdict

_ROLE_FIT_AXIS_KEYS = frozenset({"keyword_presence", "keyword_dual_placement", "tone_alignment"})
_ROLE_FIT_MAX = 40.0
_QUALITY_MAX = 60.0


def _axis_points(result: ResumeQualityResult, keys: frozenset[str]) -> float:
    return sum(axis.score for axis in result.axes if axis.key in keys)


def _pct(points: float, maximum: float) -> int:
    if maximum <= 0:
        return 0
    return max(0, min(100, round(100 * points / maximum)))


def compute_recoverable_ceiling(result: ResumeQualityResult) -> int:
    """Headroom recoverable by rewording — not by inventing skills."""
    recoverable = float(result.ats_score)
    for axis in result.axes:
        if axis.key == "keyword_presence":
            gap = axis.max_score - axis.score
            if result.single_section_keywords:
                recoverable += gap * 0.85
            elif result.missing_keywords:
                recoverable += gap * 0.6
            else:
                recoverable += gap
        elif axis.key == "keyword_dual_placement":
            recoverable += axis.max_score - axis.score
        elif axis.key in {
            "bullet_metrics",
            "action_verbs",
            "bullet_length",
            "weak_phrases",
            "resume_length",
            "first_person",
            "buzzwords",
            "section_completeness",
            "contact_completeness",
            "field_completeness",
        }:
            recoverable += axis.max_score - axis.score

    recoverable_int = round(recoverable)
    return max(result.ats_score, min(result.score_ceiling, recoverable_int, 100))


def _tailor_verdict(
    *,
    ats_score: int,
    role_fit_pct: int,
    quality_pct: int,
    recoverable_ceiling: int,
    missing_count: int,
) -> tuple[TailorVerdict, str]:
    gap = recoverable_ceiling - ats_score
    if quality_pct >= 75 and role_fit_pct >= 75:
        return (
            "fix_format_only",
            "Keywords and formatting are already strong — only minor polish remains.",
        )
    if role_fit_pct < 25 and missing_count >= 4 and quality_pct < 50:
        return (
            "skip",
            "Several core requirements do not appear on this resume. Tailoring cannot invent experience — consider a closer-matched role.",
        )
    if gap >= 12 and role_fit_pct >= 40:
        return (
            "worth_it",
            "Your background likely fits — the gap is mostly wording and keyword placement, not missing skills.",
        )
    if gap >= 8:
        return (
            "maybe",
            "Tailoring may help if you genuinely have the missing skills listed below.",
        )
    return (
        "fix_format_only",
        "Small edits could close the remaining gap.",
    )


def _score_meaning(
    *,
    ats_score: int,
    quality_pct: int,
    role_fit_pct: int,
    recoverable_ceiling: int,
) -> str:
    return (
        f"This {ats_score}/100 score measures resume structure and keyword alignment for this job — "
        f"not whether a recruiter will hire you. "
        f"Resume quality: {quality_pct}/100 (bullets, metrics, format). "
        f"Role fit: {role_fit_pct}/100 (keywords for this posting). "
        f"Rewording could reach about {recoverable_ceiling}/100 without claiming new skills."
    )


def _top_actions(blocking: list[BlockingIssue], limit: int = 5) -> list[str]:
    return [issue.suggestion.strip() for issue in blocking[:limit] if issue.suggestion.strip()]


def build_checkup_guidance(
    score_result: ResumeQualityResult,
    *,
    blocking_issues: list[BlockingIssue] | None = None,
) -> CheckupGuidance:
    all_keys = frozenset(axis.key for axis in score_result.axes)
    role_points = _axis_points(score_result, _ROLE_FIT_AXIS_KEYS)
    quality_points = _axis_points(score_result, all_keys - _ROLE_FIT_AXIS_KEYS)
    role_fit_pct = _pct(role_points, _ROLE_FIT_MAX)
    quality_pct = _pct(quality_points, _QUALITY_MAX)
    recoverable = compute_recoverable_ceiling(score_result)
    verdict, reason = _tailor_verdict(
        ats_score=score_result.ats_score,
        role_fit_pct=role_fit_pct,
        quality_pct=quality_pct,
        recoverable_ceiling=recoverable,
        missing_count=len(score_result.missing_keywords),
    )
    return CheckupGuidance(
        resume_quality_score=quality_pct,
        role_fit_score=role_fit_pct,
        recoverable_ceiling=recoverable,
        score_meaning=_score_meaning(
            ats_score=score_result.ats_score,
            quality_pct=quality_pct,
            role_fit_pct=role_fit_pct,
            recoverable_ceiling=recoverable,
        ),
        tailor_verdict=verdict,
        tailor_reason=reason,
        top_actions=_top_actions(blocking_issues or []),
    )
