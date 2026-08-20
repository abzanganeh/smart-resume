"""Deterministic fit insights for suggested job titles vs a master resume."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

_SENIOR_MARKERS = frozenset({"senior", "staff", "principal", "lead", "manager", "director", "head"})
_JUNIOR_MARKERS = frozenset({"junior", "associate", "entry", "intern"})

_SKILL_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("python", "django", "fastapi", "flask"), "Python backend development"),
    (("react", "typescript", "javascript", "frontend"), "frontend engineering"),
    (("react native", "mobile", "ios", "android", "flutter"), "mobile development"),
    (("kubernetes", "docker", "aws", "cloud", "terraform"), "cloud and platform work"),
    (("machine learning", "ml", "pytorch", "tensorflow"), "machine learning"),
    (("postgres", "sql", "database"), "database engineering"),
    (("qa", "test", "automation", "sdet"), "quality and test automation"),
]


@dataclass(frozen=True)
class TitleFitInsight:
    title: str
    fit_score: int
    strengths: list[str]
    weaknesses: list[str]


def _title_tokens(title: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", title.casefold())
    return [t for t in raw if t not in _STOP_WORDS and len(t) > 1]


def _resume_blob(resume_text: str) -> str:
    return resume_text.casefold()


def _held_match(title: str, held_titles: list[str]) -> bool:
    key = title.casefold()
    return any(key == held.casefold() for held in held_titles)


def _held_partial_match(title: str, held_titles: list[str]) -> bool:
    tokens = set(_title_tokens(title))
    if not tokens:
        return False
    for held in held_titles:
        held_tokens = set(_title_tokens(held))
        overlap = tokens & held_tokens
        if len(overlap) >= max(1, len(tokens) // 2):
            return True
    return False


def _seniority_level(title: str) -> str:
    tokens = set(_title_tokens(title))
    if tokens & _SENIOR_MARKERS:
        return "senior"
    if tokens & _JUNIOR_MARKERS:
        return "junior"
    return "mid"


def _resume_seniority(resume_text: str, held_titles: list[str]) -> str:
    blob = _resume_blob(resume_text)
    combined = " ".join(held_titles).casefold()
    if any(m in blob or m in combined for m in _SENIOR_MARKERS):
        return "senior"
    if any(m in blob or m in combined for m in _JUNIOR_MARKERS):
        return "junior"
    if re.search(r"\b(8|9|10|\d{2})\+?\s*years?\b", blob):
        return "senior"
    if re.search(r"\b[5-7]\+?\s*years?\b", blob):
        return "mid"
    return "mid"


def _matched_skill_labels(title: str, resume_text: str) -> list[str]:
    blob = _resume_blob(resume_text)
    title_blob = title.casefold()
    labels: list[str] = []
    for keywords, label in _SKILL_HINTS:
        in_title = any(kw in title_blob for kw in keywords)
        in_resume = any(kw in blob for kw in keywords)
        if in_title and in_resume:
            labels.append(label)
        elif in_resume and any(kw in title_blob for kw in keywords[:2]):
            labels.append(label)
    return labels[:3]


def _missing_skill_labels(title: str, resume_text: str) -> list[str]:
    blob = _resume_blob(resume_text)
    title_blob = title.casefold()
    missing: list[str] = []
    for keywords, label in _SKILL_HINTS:
        implied = any(kw in title_blob for kw in keywords)
        present = any(kw in blob for kw in keywords)
        if implied and not present:
            missing.append(label)
    return missing[:2]


def score_title_fit(
    title: str,
    *,
    resume_text: str,
    held_titles: list[str],
    parsed_sections: dict[str, Any] | None = None,
) -> TitleFitInsight:
    """Compute deterministic fit score and narrative strengths/weaknesses."""
    del parsed_sections  # reserved for future structured signals

    blob = _resume_blob(resume_text)
    tokens = _title_tokens(title)
    score = 58

    if _held_match(title, held_titles):
        score += 32
    elif _held_partial_match(title, held_titles):
        score += 18

    if tokens:
        hits = sum(1 for tok in tokens if tok in blob)
        ratio = hits / len(tokens)
        score += int(ratio * 22)

    matched_skills = _matched_skill_labels(title, resume_text)
    if matched_skills:
        score += min(12, 4 * len(matched_skills))

    title_level = _seniority_level(title)
    resume_level = _resume_seniority(resume_text, held_titles)
    if title_level == "senior" and resume_level != "senior":
        score -= 14
    elif title_level == "junior" and resume_level == "senior":
        score -= 6

    score = max(45, min(98, score))

    strengths: list[str] = []
    if _held_match(title, held_titles):
        strengths.append("You have held this title before — strong direct match.")
    elif _held_partial_match(title, held_titles):
        strengths.append("Closely related to titles already on your resume.")
    for label in matched_skills[:2]:
        strengths.append(f"Resume shows solid {label} experience.")
    if not strengths:
        overlap = [t for t in tokens if t in blob]
        if overlap:
            strengths.append(
                f"Resume mentions {', '.join(overlap[:3])} — relevant to this role."
            )
        else:
            strengths.append("Reasonable adjacent role based on your overall experience.")

    weaknesses: list[str] = []
    for label in _missing_skill_labels(title, resume_text):
        weaknesses.append(f"Limited evidence of {label} — consider highlighting projects that show it.")
    if title_level == "senior" and resume_level != "senior":
        weaknesses.append("Title signals senior scope — your resume may read more mid-level today.")
    if not weaknesses and score < 80:
        weaknesses.append("Stretch role — tailor bullets toward this title when you apply.")

    return TitleFitInsight(
        title=title,
        fit_score=score,
        strengths=strengths[:3],
        weaknesses=weaknesses[:2],
    )


def enrich_title_suggestions(
    titles: list[str],
    *,
    resume_text: str,
    held_titles: list[str],
    parsed_sections: dict[str, Any] | None = None,
) -> list[TitleFitInsight]:
    """Score and narrate each suggested title; highest fit first."""
    insights = [
        score_title_fit(
            title,
            resume_text=resume_text,
            held_titles=held_titles,
            parsed_sections=parsed_sections,
        )
        for title in titles
    ]
    return sorted(insights, key=lambda row: row.fit_score, reverse=True)
