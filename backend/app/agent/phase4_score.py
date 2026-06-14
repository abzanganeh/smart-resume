"""Deterministic resume quality engine for the Phase 4 ATS score.

Why this exists
---------------
The Phase 4 LLM produces narrative blocking_issues that read well, but its
numeric ``ats_score`` swings 5-10 points between identical runs because LLMs
sample stochastically and round to "nice" numbers. This module replaces that
noisy score with a deterministic, repeatable one grounded in established
resume-writing research (JobRight's keyword-density model, Resume Worded's
bullet-strength heuristics, the Harvard Career Center bullet template, etc.).

Score model
-----------
Each axis carries a fixed weight in [0, 100]. All weights sum to exactly 100,
so the final ``ats_score`` lives in the [0, 100] range without normalization.
Every axis exposes a ``status`` (pass/warn/fail) and an ``issues`` list that
the caller turns into ``blocking_issues``. This is what powers the per-axis
breakdown panel in the UI.

Public surface
--------------
* :class:`AxisScore` — per-axis result (name, score, max, status, issues).
* :class:`ResumeQualityResult` — top-level result returned by the engine.
* :func:`compute_ats_score` — single entry point used by Phase 4 + tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.agent.phase3_postprocess import flatten_skill_terms

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_DIGIT = re.compile(r"\d")
_WORD = re.compile(r"\b[\w'-]+\b")
_FIRST_PERSON = re.compile(
    r"\b(?:i|me|my|mine|myself|i'm|i've|i'll|i'd)\b",
    re.IGNORECASE,
)

# Weak openers — bullets starting with these read as passive / responsibility-
# first phrasing, the #1 thing recruiters and Resume Worded flag against.
_WEAK_PHRASES = (
    "responsible for",
    "worked on",
    "helped with",
    "helped to",
    "tasked with",
    "duties included",
    "in charge of",
    "assisted with",
    "assisted in",
    "contributed to",
    "involved in",
    "participated in",
    "exposure to",
    "familiar with",
    "knowledge of",
    "ability to",
)

# Industry-cliche buzzwords that recruiters universally treat as filler.
# Source: LinkedIn's "overused buzzwords" list + Resume Worded's cliche bank.
_BUZZWORDS = (
    "team player",
    "self-starter",
    "go-getter",
    "results-driven",
    "results-oriented",
    "detail-oriented",
    "hard worker",
    "hard-working",
    "go above and beyond",
    "think outside the box",
    "synergy",
    "synergies",
    "best of breed",
    "value add",
    "value-add",
    "guru",
    "rockstar",
    "ninja",
    "thought leader",
    "passionate about",
)

# Strong action verbs — bullets that start with one of these score full marks
# on the action-verb axis. We don't list every verb in the English language;
# this is the "high-impact" subset commonly recommended by career coaches.
_STRONG_VERBS = frozenset(
    {
        "achieved", "accelerated", "advanced", "advised", "analyzed", "architected",
        "automated", "boosted", "built", "captured", "centralized", "collaborated",
        "consolidated", "conceptualized", "cut", "decreased", "delivered", "deployed",
        "designed", "developed", "directed", "doubled", "drove", "earned", "eliminated",
        "engineered", "enhanced", "established", "executed", "expanded", "facilitated",
        "founded", "generated", "grew", "guided", "headed", "implemented", "improved",
        "increased", "influenced", "initiated", "innovated", "instituted", "integrated",
        "introduced", "invented", "launched", "led", "leveraged", "managed", "mentored",
        "migrated", "modernized", "monetized", "negotiated", "optimized", "orchestrated",
        "overhauled", "owned", "partnered", "pioneered", "planned", "prevented",
        "produced", "programmed", "promoted", "prototyped", "rebuilt", "redesigned",
        "reduced", "refactored", "researched", "resolved", "restructured", "saved",
        "scaled", "secured", "shipped", "simplified", "spearheaded", "standardized",
        "streamlined", "supervised", "surpassed", "tested", "tracked", "trained",
        "transformed", "translated", "tripled", "unified", "validated", "won",
    }
)

_BULLET_LENGTH_MIN = 8
_BULLET_LENGTH_MAX = 30
_BULLET_LENGTH_SWEET_LOW = 12
_BULLET_LENGTH_SWEET_HIGH = 25

_PAGE_CHAR_BUDGET = 3500  # rough char budget for one US-letter page in Calibri 11

# Axis weights — must sum to exactly 100. Grouped for narrative.
_W_KEYWORD_PRESENCE = 30
_W_KEYWORD_DUAL = 10
_W_SECTION_COMPLETENESS = 5
_W_CONTACT = 5
_W_METRICS = 15
_W_ACTION_VERBS = 10
_W_BULLET_LENGTH = 5
_W_RESUME_LENGTH = 5
_W_WEAK_PHRASES = 5
_W_FIRST_PERSON = 5
_W_BUZZWORDS = 5

assert (
    _W_KEYWORD_PRESENCE
    + _W_KEYWORD_DUAL
    + _W_SECTION_COMPLETENESS
    + _W_CONTACT
    + _W_METRICS
    + _W_ACTION_VERBS
    + _W_BULLET_LENGTH
    + _W_RESUME_LENGTH
    + _W_WEAK_PHRASES
    + _W_FIRST_PERSON
    + _W_BUZZWORDS
) == 100, "Axis weights must sum to 100"


Status = Literal["pass", "warn", "fail"]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class AxisScore:
    """Score for a single resume-quality axis."""

    key: str
    label: str
    score: float
    max_score: float
    status: Status
    summary: str = ""
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 1),
            "max": round(self.max_score, 1),
            "status": self.status,
            "summary": self.summary,
            "issues": list(self.issues),
        }


@dataclass
class ResumeQualityResult:
    ats_score: int
    score_ceiling: int
    axes: list[AxisScore]
    missing_keywords: list[str]
    single_section_keywords: list[str]
    keyword_section_map: dict[str, list[str]]

    @property
    def breakdown(self) -> dict[str, float]:
        """Legacy flat breakdown kept for older tests / log lines."""
        return {axis.key: axis.score for axis in self.axes}

    def to_payload(self) -> dict:
        return {
            "ats_score": self.ats_score,
            "score_ceiling": self.score_ceiling,
            "axes": [a.to_dict() for a in self.axes],
            "missing_keywords": list(self.missing_keywords),
            "single_section_keywords": list(self.single_section_keywords),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section_texts(tailored) -> dict[str, str]:
    """Return lowercased text per section used for keyword matching."""

    skills_flat = flatten_skill_terms(getattr(tailored, "skills", []) or [])
    summary_text = getattr(tailored, "summary", "") or ""

    exp_parts: list[str] = []
    for entry in getattr(tailored, "experience", []) or []:
        exp_parts.append(getattr(entry, "title", "") or "")
        exp_parts.extend(getattr(entry, "bullets", []) or [])
    experience_text = "\n".join(p for p in exp_parts if p)

    proj_parts: list[str] = []
    for entry in getattr(tailored, "projects", []) or []:
        if isinstance(entry, dict):
            for v in entry.values():
                if isinstance(v, str):
                    proj_parts.append(v)
                elif isinstance(v, list):
                    proj_parts.extend(s for s in v if isinstance(s, str))
    projects_text = "\n".join(p for p in proj_parts if p)

    return {
        "skills": " | ".join(skills_flat).lower(),
        "summary": summary_text.lower(),
        # Projects roll into Experience for ATS purposes — both are
        # "where you applied the skill" sections from a recruiter's POV.
        "experience": (experience_text + "\n" + projects_text).lower(),
    }


def _all_bullets(tailored) -> list[str]:
    bullets: list[str] = []
    for entry in getattr(tailored, "experience", []) or []:
        bullets.extend(getattr(entry, "bullets", []) or [])
    for entry in getattr(tailored, "projects", []) or []:
        if isinstance(entry, dict):
            for v in entry.values():
                if isinstance(v, list):
                    bullets.extend(b for b in v if isinstance(b, str))
    return [b for b in bullets if b and b.strip()]


def _word_count(text: str) -> int:
    return len(_WORD.findall(text or ""))


def _first_word(bullet: str) -> str:
    match = _WORD.search(bullet or "")
    return match.group(0).lower() if match else ""


def _contact_value(contact: object, key: str) -> str:
    if isinstance(contact, dict):
        return str(contact.get(key, "") or "")
    return str(getattr(contact, key, "") or "")


def _normalize(term: str) -> str:
    return (term or "").strip().lower()


def _status_from_ratio(ratio: float, *, pass_at: float = 0.9, warn_at: float = 0.7) -> Status:
    if ratio >= pass_at:
        return "pass"
    if ratio >= warn_at:
        return "warn"
    return "fail"


# ---------------------------------------------------------------------------
# Axis builders
# ---------------------------------------------------------------------------


def _axis_keyword_presence(
    keywords: list[str],
    sections: dict[str, str],
) -> tuple[AxisScore, list[str], list[str], dict[str, list[str]]]:
    if not keywords:
        return (
            AxisScore(
                key="keyword_presence",
                label="Keyword coverage",
                score=_W_KEYWORD_PRESENCE,
                max_score=_W_KEYWORD_PRESENCE,
                status="pass",
                summary="No must-have keywords parsed from the JD.",
            ),
            [],
            [],
            {},
        )

    section_map: dict[str, list[str]] = {}
    missing: list[str] = []
    single: list[str] = []
    present_count = 0
    dual_count = 0
    for kw in keywords:
        kw_lower = _normalize(kw)
        sections_present = [s for s, text in sections.items() if kw_lower and kw_lower in text]
        section_map[kw] = sections_present
        if sections_present:
            present_count += 1
            if len(sections_present) >= 2:
                dual_count += 1
            else:
                single.append(kw)
        else:
            missing.append(kw)

    coverage = present_count / len(keywords)
    score = coverage * _W_KEYWORD_PRESENCE
    status = _status_from_ratio(coverage)
    summary = (
        f"{present_count}/{len(keywords)} must-have keywords present "
        f"({round(coverage * 100)}% coverage)."
    )
    issues = [f"Missing keyword: {kw}" for kw in missing]

    axis_presence = AxisScore(
        key="keyword_presence",
        label="Keyword coverage",
        score=score,
        max_score=_W_KEYWORD_PRESENCE,
        status=status,
        summary=summary,
        issues=issues,
    )
    return axis_presence, missing, single, section_map


def _axis_keyword_dual(
    keywords: list[str],
    section_map: dict[str, list[str]],
    single: list[str],
) -> AxisScore:
    if not keywords:
        return AxisScore(
            key="keyword_dual_placement",
            label="Dual placement (Skills + Experience/Summary)",
            score=_W_KEYWORD_DUAL,
            max_score=_W_KEYWORD_DUAL,
            status="pass",
            summary="No must-have keywords parsed from the JD.",
        )

    dual_count = sum(1 for kw in keywords if len(section_map.get(kw, [])) >= 2)
    ratio = dual_count / len(keywords)
    score = ratio * _W_KEYWORD_DUAL
    issues = [f"'{kw}' appears in only one section" for kw in single]
    return AxisScore(
        key="keyword_dual_placement",
        label="Dual placement (Skills + Experience/Summary)",
        score=score,
        max_score=_W_KEYWORD_DUAL,
        status=_status_from_ratio(ratio, pass_at=0.8, warn_at=0.5),
        summary=(
            f"{dual_count}/{len(keywords)} keywords appear in 2+ sections — "
            "ATS systems weight density across sections, not just presence."
        ),
        issues=issues,
    )


def _axis_metrics(bullets: list[str]) -> AxisScore:
    if not bullets:
        return AxisScore(
            key="bullet_metrics",
            label="Quantified bullets",
            score=0,
            max_score=_W_METRICS,
            status="fail",
            summary="No experience or project bullets to score.",
            issues=["Add at least one experience bullet so this axis can score."],
        )
    with_metric = sum(1 for b in bullets if _DIGIT.search(b))
    ratio = with_metric / len(bullets)
    score = ratio * _W_METRICS
    unquantified = [b for b in bullets if not _DIGIT.search(b)]
    issues = [
        f"Add a metric to: {b[:80]}{'…' if len(b) > 80 else ''}"
        for b in unquantified[:5]
    ]
    return AxisScore(
        key="bullet_metrics",
        label="Quantified bullets",
        score=score,
        max_score=_W_METRICS,
        status=_status_from_ratio(ratio, pass_at=0.85, warn_at=0.6),
        summary=f"{with_metric}/{len(bullets)} bullets contain a number or percentage.",
        issues=issues,
    )


def _axis_action_verbs(bullets: list[str]) -> AxisScore:
    if not bullets:
        return AxisScore(
            key="action_verbs",
            label="Strong action verbs",
            score=_W_ACTION_VERBS,
            max_score=_W_ACTION_VERBS,
            status="pass",
            summary="No bullets to analyze.",
        )

    strong_count = 0
    weak_examples: list[str] = []
    for bullet in bullets:
        first = _first_word(bullet)
        if first in _STRONG_VERBS:
            strong_count += 1
        elif first:
            weak_examples.append(bullet)

    ratio = strong_count / len(bullets)
    score = ratio * _W_ACTION_VERBS
    issues = [
        f"Open with a stronger verb: {b[:80]}{'…' if len(b) > 80 else ''}"
        for b in weak_examples[:5]
    ]
    return AxisScore(
        key="action_verbs",
        label="Strong action verbs",
        score=score,
        max_score=_W_ACTION_VERBS,
        status=_status_from_ratio(ratio, pass_at=0.85, warn_at=0.6),
        summary=(
            f"{strong_count}/{len(bullets)} bullets open with a high-impact verb "
            "(led, built, shipped, reduced, ...)."
        ),
        issues=issues,
    )


def _axis_bullet_length(bullets: list[str]) -> AxisScore:
    if not bullets:
        return AxisScore(
            key="bullet_length",
            label="Bullet length sweet spot",
            score=_W_BULLET_LENGTH,
            max_score=_W_BULLET_LENGTH,
            status="pass",
            summary="No bullets to analyze.",
        )

    in_range = 0
    too_short: list[str] = []
    too_long: list[str] = []
    for bullet in bullets:
        wc = _word_count(bullet)
        if _BULLET_LENGTH_SWEET_LOW <= wc <= _BULLET_LENGTH_SWEET_HIGH:
            in_range += 1
        elif wc < _BULLET_LENGTH_SWEET_LOW:
            too_short.append(bullet)
        else:
            too_long.append(bullet)

    ratio = in_range / len(bullets)
    score = ratio * _W_BULLET_LENGTH
    issues: list[str] = []
    for b in too_short[:3]:
        issues.append(f"Bullet too short ({_word_count(b)} words): {b[:80]}{'…' if len(b) > 80 else ''}")
    for b in too_long[:3]:
        issues.append(f"Bullet too long ({_word_count(b)} words): {b[:80]}{'…' if len(b) > 80 else ''}")

    return AxisScore(
        key="bullet_length",
        label="Bullet length sweet spot (12-25 words)",
        score=score,
        max_score=_W_BULLET_LENGTH,
        status=_status_from_ratio(ratio, pass_at=0.8, warn_at=0.5),
        summary=f"{in_range}/{len(bullets)} bullets are 12-25 words (recruiter scan zone).",
        issues=issues,
    )


def _axis_resume_length(tailored, career_stage: str) -> AxisScore:
    """Estimate page count and check it against career-stage expectations."""

    parts: list[str] = []
    parts.append(getattr(tailored, "summary", "") or "")
    parts.extend(getattr(tailored, "skills", []) or [])
    for entry in getattr(tailored, "experience", []) or []:
        parts.append(getattr(entry, "title", "") or "")
        parts.append(getattr(entry, "company", "") or "")
        parts.append(getattr(entry, "dates", "") or "")
        parts.extend(getattr(entry, "bullets", []) or [])
    for entry in getattr(tailored, "projects", []) or []:
        if isinstance(entry, dict):
            for v in entry.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    parts.extend(str(x) for x in v if isinstance(x, str))

    char_count = sum(len(p) for p in parts if p)
    pages_estimate = char_count / _PAGE_CHAR_BUDGET

    expected = 2.0 if career_stage == "senior" else 1.0

    if pages_estimate <= expected + 0.1:
        score = _W_RESUME_LENGTH
        status: Status = "pass"
        summary = f"Estimated {pages_estimate:.1f} pages (target ≤ {expected:g} for {career_stage})."
        issues: list[str] = []
    elif pages_estimate <= expected + 0.5:
        score = _W_RESUME_LENGTH * 0.6
        status = "warn"
        summary = f"Estimated {pages_estimate:.1f} pages — slightly over the {expected:g}-page target."
        issues = ["Trim oldest or least-relevant bullets to stay within target page count."]
    else:
        score = _W_RESUME_LENGTH * 0.2
        status = "fail"
        summary = f"Estimated {pages_estimate:.1f} pages — well over the {expected:g}-page target."
        issues = [
            "Resume is too long. Cut bullets from older roles, drop projects unrelated to the JD, "
            "and keep the current role at ≤ 5 bullets."
        ]
    return AxisScore(
        key="resume_length",
        label="Resume length",
        score=score,
        max_score=_W_RESUME_LENGTH,
        status=status,
        summary=summary,
        issues=issues,
    )


def _axis_section_completeness(tailored) -> AxisScore:
    has_summary = bool((getattr(tailored, "summary", "") or "").strip())
    has_skills = bool(flatten_skill_terms(getattr(tailored, "skills", []) or []))
    has_experience = bool(getattr(tailored, "experience", []) or [])
    full = int(has_summary) + int(has_skills) + int(has_experience)
    ratio = full / 3
    issues: list[str] = []
    if not has_summary:
        issues.append("Add a Professional Summary section (3-5 lines).")
    if not has_skills:
        issues.append("Add a Skills section grouped into 3-5 categories.")
    if not has_experience:
        issues.append("Add at least one Experience entry.")
    return AxisScore(
        key="section_completeness",
        label="Section completeness",
        score=ratio * _W_SECTION_COMPLETENESS,
        max_score=_W_SECTION_COMPLETENESS,
        status=_status_from_ratio(ratio, pass_at=1.0, warn_at=0.66),
        summary=f"{full}/3 core sections populated (Summary, Skills, Experience).",
        issues=issues,
    )


def _axis_contact(tailored) -> AxisScore:
    contact = getattr(tailored, "contact", None)
    has_name = bool(_contact_value(contact, "name").strip())
    has_email = bool(_contact_value(contact, "email").strip())
    earned = (int(has_name) + int(has_email)) / 2
    issues: list[str] = []
    if not has_name:
        issues.append("Add your full name to the contact header.")
    if not has_email:
        issues.append("Add a professional email to the contact header.")
    return AxisScore(
        key="contact_completeness",
        label="Contact details",
        score=earned * _W_CONTACT,
        max_score=_W_CONTACT,
        status=_status_from_ratio(earned, pass_at=1.0, warn_at=0.5),
        summary="Name and email present." if earned == 1 else "Contact header is incomplete.",
        issues=issues,
    )


def _axis_weak_phrases(bullets: list[str]) -> AxisScore:
    offenders: list[tuple[str, str]] = []
    for bullet in bullets:
        lowered = bullet.lower()
        for phrase in _WEAK_PHRASES:
            if phrase in lowered:
                offenders.append((phrase, bullet))
                break

    if not bullets:
        return AxisScore(
            key="weak_phrases",
            label="No weak phrasing",
            score=_W_WEAK_PHRASES,
            max_score=_W_WEAK_PHRASES,
            status="pass",
            summary="No bullets to analyze.",
        )

    offending_count = len(offenders)
    score = max(0.0, _W_WEAK_PHRASES - offending_count)  # 1 pt per offender, floored at 0
    status: Status = "pass" if offending_count == 0 else ("warn" if offending_count <= 2 else "fail")
    issues = [
        f"Replace '{phrase}' in: {bullet[:80]}{'…' if len(bullet) > 80 else ''}"
        for phrase, bullet in offenders[:5]
    ]
    return AxisScore(
        key="weak_phrases",
        label="No weak phrasing",
        score=score,
        max_score=_W_WEAK_PHRASES,
        status=status,
        summary=(
            "Bullets read with strong, ownership-first phrasing."
            if offending_count == 0
            else f"{offending_count} bullets use weak openers like 'responsible for' or 'worked on'."
        ),
        issues=issues,
    )


def _axis_first_person(bullets: list[str], summary: str) -> AxisScore:
    offenders: list[str] = []
    if summary and _FIRST_PERSON.search(summary):
        offenders.append(summary)
    for bullet in bullets:
        if _FIRST_PERSON.search(bullet):
            offenders.append(bullet)

    if not offenders:
        score = _W_FIRST_PERSON
        status: Status = "pass"
        summary_text = "No first-person pronouns detected."
        issues: list[str] = []
    else:
        score = max(0.0, _W_FIRST_PERSON - len(offenders))
        status = "warn" if len(offenders) <= 2 else "fail"
        summary_text = (
            f"{len(offenders)} bullets/sentences use first-person pronouns "
            "(I, my, me) — resumes are written in implied first person."
        )
        issues = [
            f"Remove first-person pronoun from: {b[:80]}{'…' if len(b) > 80 else ''}"
            for b in offenders[:5]
        ]
    return AxisScore(
        key="first_person",
        label="No first-person pronouns",
        score=score,
        max_score=_W_FIRST_PERSON,
        status=status,
        summary=summary_text,
        issues=issues,
    )


def _axis_buzzwords(bullets: list[str], summary: str) -> AxisScore:
    haystack = (summary or "").lower() + "\n" + "\n".join(b.lower() for b in bullets)
    hits: list[str] = []
    for phrase in _BUZZWORDS:
        if phrase in haystack:
            hits.append(phrase)
    if not hits:
        score = _W_BUZZWORDS
        status: Status = "pass"
        summary_text = "No cliche buzzwords detected."
        issues: list[str] = []
    else:
        score = max(0.0, _W_BUZZWORDS - len(hits))
        status = "warn" if len(hits) <= 2 else "fail"
        summary_text = f"{len(hits)} buzzwords detected: {', '.join(hits[:5])}"
        issues = [f"Remove buzzword '{p}' — replace with a concrete accomplishment." for p in hits[:5]]
    return AxisScore(
        key="buzzwords",
        label="No filler buzzwords",
        score=score,
        max_score=_W_BUZZWORDS,
        status=status,
        summary=summary_text,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_ats_score(
    tailored,
    must_have_keywords: Iterable[str],
    *,
    career_stage: str = "mid",
) -> ResumeQualityResult:
    """Compute a deterministic 0-100 resume quality score.

    The score is the sum of 11 axes whose weights total 100. Each axis is a
    pure function of the resume content and the JD must-have list, so an
    identical input always produces an identical score — no LLM noise.
    """

    keywords = [k for k in must_have_keywords if k and k.strip()]
    sections = _section_texts(tailored)
    bullets = _all_bullets(tailored)
    summary_text = getattr(tailored, "summary", "") or ""

    axis_presence, missing, single, section_map = _axis_keyword_presence(keywords, sections)
    axes = [
        axis_presence,
        _axis_keyword_dual(keywords, section_map, single),
        _axis_section_completeness(tailored),
        _axis_contact(tailored),
        _axis_metrics(bullets),
        _axis_action_verbs(bullets),
        _axis_bullet_length(bullets),
        _axis_resume_length(tailored, career_stage),
        _axis_weak_phrases(bullets),
        _axis_first_person(bullets, summary_text),
        _axis_buzzwords(bullets, summary_text),
    ]

    raw = sum(axis.score for axis in axes)
    ats_score = max(0, min(100, round(raw)))
    headroom = sum(axis.max_score - axis.score for axis in axes)
    score_ceiling = max(ats_score, min(100, ats_score + round(headroom * 0.85)))

    return ResumeQualityResult(
        ats_score=ats_score,
        score_ceiling=score_ceiling,
        axes=axes,
        missing_keywords=missing,
        single_section_keywords=single,
        keyword_section_map=section_map,
    )
