"""Deterministic post-processing for Phase 3 tailored resume output.

LLM output is not always compliant with prompt rules (e.g. flat skills instead of
JobRight-style categories). These helpers enforce structure without touching UI
manual-edit flows.
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.agent.tone_lint import annotate_tone_alignment
from app.agent.tone_profile import JDToneProfile
from app.agent.phase3_truthfulness import TruthfulnessContext, apply_truthfulness_guards
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput

_CATEGORY_LINE_RE = re.compile(r"^([^:]+):\s*(.+)$")

# Order matters — most JD-relevant groups first when multiple rules match.
_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "AI & Machine Learning",
        re.compile(
            r"\b(generative\s*ai|llm?s?|large\s+language|rag|retrieval-augmented|"
            r"nim|nemo|pytorch|tensorflow|machine\s+learning|deep\s+learning|"
            r"transformer|embedding|gpu|model\s+training|nlp)\b",
            re.I,
        ),
    ),
    (
        "Programming Languages & Frameworks",
        re.compile(
            r"\b(python|java|javascript|typescript|go\b|rust|c\+\+|c#|sql|"
            r"fastapi|django|flask|spring|react|node\.?js|rest\s*api)\b",
            re.I,
        ),
    ),
    (
        "Cloud & Architecture",
        re.compile(
            r"\b(aws|azure|gcp|cloud|microservices|serverless|saas|"
            r"cloud-native|distributed\s+systems|architecture)\b",
            re.I,
        ),
    ),
    (
        "DevOps & Infrastructure",
        re.compile(
            r"\b(kubernetes|docker|ci/?cd|mlops|terraform|ansible|jenkins|"
            r"helm|container|infrastructure|devops|pipeline)\b",
            re.I,
        ),
    ),
    (
        "Data Engineering",
        re.compile(
            r"\b(spark|kafka|airflow|etl|data\s+pipeline|warehouse|"
            r"snowflake|databricks|dbt|data\s+engineering)\b",
            re.I,
        ),
    ),
    (
        "Security & Identity",
        re.compile(
            r"\b(oauth|saml|identity|security|auth|iam|encryption|compliance)\b",
            re.I,
        ),
    ),
]

_FALLBACK_CATEGORY = "Engineering & Tools"
_MAX_CATEGORIES = 5
_MAX_SKILLS_PER_CATEGORY = 8
_CURRENT_ROLE_MAX_BULLETS = 5
_PRIOR_ROLE_MAX_BULLETS = 3
_PROJECT_MAX_BULLETS = 3
_MAX_SKILL_WORDS = 6


def is_category_skill_line(skill: str) -> bool:
    """True when skill follows ``Category: a, b, c`` format."""
    text = skill.strip()
    if not _CATEGORY_LINE_RE.match(text):
        return False
    _, items = text.split(":", 1)
    return bool(items.strip())


def skills_are_categorized(skills: list[str]) -> bool:
    if not skills:
        return True
    categorized = sum(1 for s in skills if is_category_skill_line(s))
    return categorized >= max(1, len(skills) // 2)


def flatten_skill_terms(skills: list[str]) -> list[str]:
    """Public version: expand "Category: a, b" lines into individual skill terms.

    Used by Phase 4 keyword detection. Unlike :func:`_flatten_skills` this
    keeps every term (no word-count filter) because callers only need
    substring-match coverage, not display-quality skills.
    """
    flat: list[str] = []
    seen: set[str] = set()
    for raw in skills or []:
        text = raw.strip()
        if not text:
            continue
        if is_category_skill_line(text):
            _, items = text.split(":", 1)
            for item in items.split(","):
                term = item.strip()
                key = term.lower()
                if term and key not in seen:
                    flat.append(term)
                    seen.add(key)
            continue
        key = text.lower()
        if key not in seen:
            flat.append(text)
            seen.add(key)
    return flat


def _flatten_skills(skills: list[str]) -> list[str]:
    """Expand category lines and drop sentence-style entries."""
    flat: list[str] = []
    seen: set[str] = set()
    for raw in skills:
        text = raw.strip()
        if not text:
            continue
        if is_category_skill_line(text):
            _, items = text.split(":", 1)
            for item in items.split(","):
                term = item.strip()
                key = term.lower()
                if term and key not in seen and len(term.split()) <= _MAX_SKILL_WORDS:
                    flat.append(term)
                    seen.add(key)
            continue
        if len(text.split()) > _MAX_SKILL_WORDS:
            continue
        key = text.lower()
        if key not in seen:
            flat.append(text)
            seen.add(key)
    return flat


def _match_category(skill: str) -> str:
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(skill):
            return category
    return _FALLBACK_CATEGORY


def normalize_skills_to_categories(
    skills: list[str],
    must_have_keywords: list[str] | None = None,
) -> list[str]:
    """Group flat skills into JobRight-style category lines."""
    if skills_are_categorized(skills):
        return _trim_category_lines(skills)

    flat = _flatten_skills(skills)
    if not flat:
        return skills

    # Boost categories that appear in must-have JD keywords.
    jd_text = " ".join(must_have_keywords or []).lower()
    buckets: dict[str, list[str]] = defaultdict(list)
    for skill in flat:
        category = _match_category(skill)
        if category == _FALLBACK_CATEGORY and must_have_keywords:
            for cat_name, pattern in _CATEGORY_RULES:
                if pattern.search(jd_text):
                    category = cat_name
                    break
        if skill not in buckets[category]:
            buckets[category].append(skill)

    ordered_categories: list[str] = []
    for cat_name, _ in _CATEGORY_RULES:
        if cat_name in buckets:
            ordered_categories.append(cat_name)
    if _FALLBACK_CATEGORY in buckets and _FALLBACK_CATEGORY not in ordered_categories:
        ordered_categories.append(_FALLBACK_CATEGORY)

    result: list[str] = []
    for cat in ordered_categories[:_MAX_CATEGORIES]:
        items = buckets[cat][:_MAX_SKILLS_PER_CATEGORY]
        if items:
            result.append(f"{cat}: {', '.join(items)}")

    return result or skills


def _trim_category_lines(skills: list[str]) -> list[str]:
    trimmed: list[str] = []
    for line in skills[:_MAX_CATEGORIES]:
        if not is_category_skill_line(line):
            trimmed.append(line)
            continue
        name, items = line.split(":", 1)
        parts = [p.strip() for p in items.split(",") if p.strip()]
        trimmed.append(f"{name.strip()}: {', '.join(parts[:_MAX_SKILLS_PER_CATEGORY])}")
    return trimmed


def enforce_experience_bullet_limits(
    experience: list[TailoredExperienceEntry],
) -> list[TailoredExperienceEntry]:
    """Current role ≤5 bullets; prior roles ≤3."""
    if not experience:
        return experience

    updated: list[TailoredExperienceEntry] = []
    for idx, entry in enumerate(experience):
        limit = _CURRENT_ROLE_MAX_BULLETS if idx == 0 else _PRIOR_ROLE_MAX_BULLETS
        if len(entry.bullets) <= limit:
            updated.append(entry)
            continue
        trimmed = entry.model_copy(
            update={
                "bullets": entry.bullets[:limit],
                "removed_bullets": [
                    *entry.removed_bullets,
                    *entry.bullets[limit:],
                ],
            }
        )
        updated.append(trimmed)
    return updated


def enforce_project_bullet_limits(projects: list[dict]) -> list[dict]:
    """Each project ≤3 bullets."""
    updated: list[dict] = []
    for proj in projects:
        if not isinstance(proj, dict):
            updated.append(proj)
            continue
        bullets = proj.get("bullets") or []
        if not isinstance(bullets, list) or len(bullets) <= _PROJECT_MAX_BULLETS:
            updated.append(proj)
            continue
        copy = dict(proj)
        copy["bullets"] = bullets[:_PROJECT_MAX_BULLETS]
        updated.append(copy)
    return updated


def postprocess_tailored_output(
    output: TailoredResumeOutput,
    must_have_keywords: list[str] | None = None,
    tone_profile: JDToneProfile | None = None,
    truthfulness: TruthfulnessContext | None = None,
) -> TailoredResumeOutput:
    """Apply deterministic structure rules after LLM generation.

    ``tone_profile`` — when supplied and non-neutral — triggers a tone lint
    pass that appends non-mutating findings to ``rewrite_notes``. Bullets
    themselves are never rewritten here; auto-repair would just be
    fabrication pressure by another name.
    """
    skills = normalize_skills_to_categories(output.skills, must_have_keywords)
    experience = enforce_experience_bullet_limits(output.experience)
    projects = enforce_project_bullet_limits(output.projects)

    notes = list(output.rewrite_notes)
    if skills != output.skills and not any("skill categor" in n.lower() for n in notes):
        notes.append(
            "Skills grouped into JD-relevant categories for ATS readability "
            "(JobRight-style format)."
        )

    interim = output.model_copy(
        update={
            "skills": skills,
            "experience": experience,
            "projects": projects,
            "rewrite_notes": notes,
        }
    )

    if tone_profile is not None:
        interim = annotate_tone_alignment(interim, tone_profile)

    if truthfulness is not None:
        interim = apply_truthfulness_guards(interim, truthfulness)

    return interim


__all__ = [
    "enforce_experience_bullet_limits",
    "enforce_project_bullet_limits",
    "flatten_skill_terms",
    "is_category_skill_line",
    "normalize_skills_to_categories",
    "postprocess_tailored_output",
    "skills_are_categorized",
]
