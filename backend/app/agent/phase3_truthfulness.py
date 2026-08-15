"""Deterministic Phase 3 truthfulness guards (Track B).

Prompt-only anti-fabrication rules are necessary but not sufficient — these
functions enforce metrics, title integrity, section completeness, and bullet
provenance after the LLM returns. On failure: flag in rewrite_notes /
metrics_needed, strip or restore — never auto-invent replacements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.rewrite import (
    MetricNeeded,
    TailoredEducationEntry,
    TailoredExperienceEntry,
    TailoredResumeOutput,
)
from app.models.session import ApprovedMetric, BulletFix
from app.models.resume import ParsedResume

_METRIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+(?:\.\d+)?%"),
    re.compile(r"\$\d+(?:\.\d+)?[KMB]?", re.I),
    re.compile(r"\d+x\b", re.I),
    re.compile(r"\d+\+"),
)

_ACCOMPLISHMENT_RE = re.compile(
    r"\b(led|built|owned|architected|spearheaded|established|delivered|created|"
    r"designed|implemented|managed|directed|headed|founded|launched|"
    r"experience (?:leading|building|owning))\b",
    re.I,
)

_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "by"}
)


@dataclass
class TruthfulnessContext:
    """Inputs required for deterministic post-LLM guards."""

    approved_metrics: list[ApprovedMetric] = field(default_factory=list)
    resume_parsed: ParsedResume | None = None
    resume_raw: str = ""
    prior_output: TailoredResumeOutput | None = None
    user_extra_notes: str = ""
    user_claimed_keywords: list[str] = field(default_factory=list)
    bullet_fixes: list[BulletFix] = field(default_factory=list)
    jd_job_title: str = ""
    must_have_keywords: list[str] = field(default_factory=list)


def _normalize_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _company_lookup(parsed: ParsedResume | None) -> dict[str, tuple[str, str, str]]:
    """Map normalized company → (title, company, dates) from parsed resume."""
    lookup: dict[str, tuple[str, str, str]] = {}
    if parsed is None:
        return lookup
    for entry in parsed.experience:
        key = _normalize_company(entry.company)
        if key:
            lookup[key] = (entry.title, entry.company, entry.dates)
    return lookup


def _prior_companies(prior: TailoredResumeOutput | None) -> set[str]:
    if prior is None:
        return set()
    return {_normalize_company(e.company) for e in prior.experience if e.company}


def _metrics_by_scope(approved: list[ApprovedMetric]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in approved:
        grouped.setdefault(_normalize_company(item.scope), []).append(item.metric)
    return grouped


def _find_metrics_in_text(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _METRIC_PATTERNS:
        found.extend(pattern.findall(text))
    return found


def _metric_allowed(number: str, scope_metrics: list[str]) -> bool:
    if not scope_metrics:
        return False
    needle = number.lower()
    return any(needle in m.lower() for m in scope_metrics)


def _strip_metric_from_bullet(bullet: str, metric: str) -> str:
    """Remove a fabricated metric clause from a bullet."""
    cleaned = bullet.replace(metric, "").strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;])", r"\1", cleaned)
    cleaned = re.sub(r"(,\s*)+,", ",", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    return cleaned.strip(" ,.;-")


def validate_bullet_metrics(
    output: TailoredResumeOutput,
    approved_metrics: list[ApprovedMetric],
) -> TailoredResumeOutput:
    """Strip numbers not present in approved_metrics for the bullet's scope."""
    if not output.experience and not output.projects:
        return output

    by_scope = _metrics_by_scope(approved_metrics)
    notes = list(output.rewrite_notes)
    metrics_needed = list(output.metrics_needed)
    updated_experience: list[TailoredExperienceEntry] = []

    for entry in output.experience:
        scope_key = _normalize_company(entry.company)
        scope_metrics = by_scope.get(scope_key, [])
        all_metrics_flat = [m for metrics in by_scope.values() for m in metrics]
        new_bullets: list[str] = []
        for idx, bullet in enumerate(entry.bullets):
            text = bullet
            for metric in _find_metrics_in_text(bullet):
                if _metric_allowed(metric, scope_metrics):
                    continue
                other_scope = next(
                    (scope for scope, metrics in by_scope.items()
                     if scope != scope_key and _metric_allowed(metric, metrics)),
                    None,
                )
                if other_scope:
                    notes.append(
                        f"Removed metric '{metric}' from {entry.company} bullet — "
                        f"belongs to another scope, not this employer."
                    )
                else:
                    notes.append(
                        f"Removed unverified metric '{metric}' from {entry.company} "
                        f"bullet — no matching entry in approved_metrics."
                    )
                text = _strip_metric_from_bullet(text, metric)
                metrics_needed.append(
                    MetricNeeded(
                        section="Professional Experience",
                        company=entry.company,
                        bullet_index=idx,
                        prompt="What was the measurable impact for this accomplishment?",
                    )
                )
            new_bullets.append(text)
        updated_experience.append(entry.model_copy(update={"bullets": new_bullets}))

    updated_projects: list[dict] = []
    for proj in output.projects:
        if not isinstance(proj, dict):
            updated_projects.append(proj)
            continue
        scope_key = _normalize_company(str(proj.get("name", "")))
        scope_metrics = by_scope.get(scope_key, [])
        bullets = proj.get("bullets") or []
        if not isinstance(bullets, list):
            updated_projects.append(proj)
            continue
        new_bullets: list[str] = []
        for idx, bullet in enumerate(bullets):
            if not isinstance(bullet, str):
                continue
            text = bullet
            for metric in _find_metrics_in_text(bullet):
                if _metric_allowed(metric, scope_metrics):
                    continue
                text = _strip_metric_from_bullet(text, metric)
                notes.append(
                    f"Removed unverified metric '{metric}' from project "
                    f"{proj.get('name', '')}."
                )
                metrics_needed.append(
                    MetricNeeded(
                        section="Projects",
                        company=str(proj.get("name", "")),
                        bullet_index=idx,
                        prompt="What was the measurable impact for this project?",
                    )
                )
            new_bullets.append(text)
        copy = dict(proj)
        copy["bullets"] = new_bullets
        updated_projects.append(copy)

    return output.model_copy(
        update={
            "experience": updated_experience,
            "projects": updated_projects,
            "rewrite_notes": notes,
            "metrics_needed": metrics_needed,
        }
    )


def enforce_entry_integrity(
    output: TailoredResumeOutput,
    resume_parsed: ParsedResume | None,
    *,
    prior: TailoredResumeOutput | None = None,
) -> TailoredResumeOutput:
    """Restore title/company/dates for existing roles; drop invented employers."""
    lookup = _company_lookup(resume_parsed)
    allowed_prior = _prior_companies(prior)
    notes = list(output.rewrite_notes)
    kept: list[TailoredExperienceEntry] = []

    for entry in output.experience:
        key = _normalize_company(entry.company)
        if key in lookup:
            orig_title, orig_company, orig_dates = lookup[key]
            updates: dict[str, str] = {}
            if entry.title != orig_title:
                notes.append(
                    f"Restored original title '{orig_title}' for {orig_company} — "
                    f"LLM output changed it to '{entry.title}'."
                )
                updates["title"] = orig_title
            if entry.company != orig_company:
                updates["company"] = orig_company
            if entry.dates != orig_dates:
                updates["dates"] = orig_dates
            kept.append(entry.model_copy(update=updates) if updates else entry)
            continue
        if key in allowed_prior:
            kept.append(entry)
            continue
        if key:
            notes.append(
                f"Dropped experience entry for '{entry.company}' — company not "
                f"found in original resume."
            )

    return output.model_copy(update={"experience": kept, "rewrite_notes": notes})


def _strip_jd_title_from_summary(summary: str, jd_title: str) -> tuple[str, list[str]]:
    if not summary or not jd_title:
        return summary, []
    title = jd_title.strip()
    if not title:
        return summary, []
    pattern = re.compile(re.escape(title), re.I)
    if not pattern.search(summary[:120]):
        return summary, []
    cleaned = pattern.sub("", summary, count=1).strip()
    cleaned = re.sub(r"^[\s,;-]+", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    note = (
        f"Removed JD job title '{title}' from summary opening — "
        "candidate has not held this exact title."
    )
    return cleaned, [note]


def restore_missing_sections(
    output: TailoredResumeOutput,
    resume_parsed: ParsedResume | None,
    *,
    prior: TailoredResumeOutput | None = None,
) -> TailoredResumeOutput:
    """Re-inject education/projects/certs silently dropped by the LLM."""
    if resume_parsed is None and prior is None:
        return output

    notes = list(output.rewrite_notes)
    education = list(output.education)
    projects = list(output.projects)
    certifications = list(output.certifications)

    if not education:
        source_edu = (
            prior.education if prior and prior.education else []
        )
        if not source_edu and resume_parsed:
            source_edu = [
                TailoredEducationEntry(
                    degree=e.degree,
                    institution=e.institution,
                    year=e.year or "",
                    bullets=[],
                )
                for e in resume_parsed.education
            ]
        if source_edu:
            education = list(source_edu)
            notes.append(
                "Restored Education section — LLM output omitted it despite "
                "being present in the original resume."
            )

    if not projects:
        source_projects = prior.projects if prior and prior.projects else []
        if not source_projects and resume_parsed:
            source_projects = [
                {
                    "name": p.name,
                    "url": p.url,
                    "bullets": list(p.bullets or []),
                    "relevant_to_jd": True,
                }
                for p in resume_parsed.projects
            ]
        if source_projects:
            projects = list(source_projects)
            notes.append(
                "Restored Projects section — LLM output omitted projects from "
                "the original resume."
            )

    if not certifications:
        source_certs = prior.certifications if prior and prior.certifications else []
        if not source_certs and resume_parsed:
            source_certs = list(resume_parsed.certifications or [])
        if source_certs:
            certifications = list(source_certs)
            notes.append(
                "Restored Certifications section dropped by LLM output."
            )

    return output.model_copy(
        update={
            "education": education,
            "projects": projects,
            "certifications": certifications,
            "rewrite_notes": notes,
        }
    )


def _provenance_corpus(ctx: TruthfulnessContext) -> str:
    parts = [ctx.resume_raw, ctx.user_extra_notes]
    parts.extend(ctx.user_claimed_keywords)
    for fix in ctx.bullet_fixes:
        parts.extend([fix.original, fix.suggestion])
    return "\n".join(p for p in parts if p).lower()


def _anchor_phrases(text: str, min_words: int = 3) -> list[str]:
    words = [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOPWORDS]
    phrases: list[str] = []
    for i in range(len(words) - min_words + 1):
        phrases.append(" ".join(words[i : i + min_words]))
    return phrases


def annotate_bullet_provenance(
    output: TailoredResumeOutput,
    ctx: TruthfulnessContext,
    *,
    min_anchor_words: int = 3,
) -> TailoredResumeOutput:
    """Flag bullets with no semantic anchor in source material."""
    corpus = _provenance_corpus(ctx)
    if not corpus.strip():
        return output

    notes = list(output.rewrite_notes)
    for entry in output.experience:
        for bullet in entry.bullets:
            if not bullet.strip():
                continue
            anchors = _anchor_phrases(bullet, min_anchor_words)
            if not anchors:
                continue
            if not any(a in corpus for a in anchors):
                notes.append(
                    f"Provenance check: {entry.company} bullet may lack source "
                    f"evidence — verify before submitting: "
                    f"{bullet[:100]}{'…' if len(bullet) > 100 else ''}"
                )

    existing = {n.strip() for n in output.rewrite_notes}
    deduped = list(output.rewrite_notes)
    for note in notes:
        if note.strip() not in existing:
            deduped.append(note)
            existing.add(note.strip())

    return output.model_copy(update={"rewrite_notes": deduped})


def apply_truthfulness_guards(
    output: TailoredResumeOutput,
    ctx: TruthfulnessContext,
) -> TailoredResumeOutput:
    """Run all deterministic truthfulness guards in dependency order."""
    result = validate_bullet_metrics(output, ctx.approved_metrics)
    result = enforce_entry_integrity(
        result, ctx.resume_parsed, prior=ctx.prior_output
    )
    result = restore_missing_sections(
        result, ctx.resume_parsed, prior=ctx.prior_output
    )

    if ctx.jd_job_title and result.summary:
        cleaned_summary, title_notes = _strip_jd_title_from_summary(
            result.summary, ctx.jd_job_title
        )
        if title_notes:
            result = result.model_copy(
                update={
                    "summary": cleaned_summary,
                    "rewrite_notes": [*result.rewrite_notes, *title_notes],
                }
            )

    result = annotate_bullet_provenance(result, ctx)
    return result


__all__ = [
    "TruthfulnessContext",
    "annotate_bullet_provenance",
    "apply_truthfulness_guards",
    "enforce_entry_integrity",
    "restore_missing_sections",
    "validate_bullet_metrics",
]
