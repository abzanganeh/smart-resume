"""Deterministic experience bullet fallback when Phase 3 LLM output is hollow."""

from __future__ import annotations

import re

from app.agent.phase3_hollow import phase3_is_hollow
from app.agent.phase3_truthfulness import _normalize_company
from app.models.audit import AuditOutput
from app.models.resume import ParsedResume
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput

_FALLBACK_NOTE = (
    "Deterministic experience fallback applied from parsed resume "
    "(LLM returned no bullets)."
)


def _company_keys(parsed: ParsedResume | None, prior: TailoredResumeOutput | None) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for source in (prior, parsed):
        if source is None:
            continue
        entries = source.experience if hasattr(source, "experience") else []
        for entry in entries:
            key = _normalize_company(entry.company)
            if key and key not in seen:
                seen.add(key)
                order.append(key)
    return order


def _prior_entry(
    prior: TailoredResumeOutput | None, norm_key: str
) -> TailoredExperienceEntry | None:
    if prior is None:
        return None
    for entry in prior.experience:
        if _normalize_company(entry.company) == norm_key:
            return entry
    return None


def _parsed_entry(parsed: ParsedResume | None, norm_key: str):
    if parsed is None:
        return None
    for entry in parsed.experience:
        if _normalize_company(entry.company) == norm_key:
            return entry
    return None


def _absorb_keyword(bullet: str, keyword: str) -> str | None:
    """Prepend a must-have keyword phrase only when it fits without new metrics."""
    kw = keyword.strip()
    if not kw or kw.lower() in bullet.lower():
        return None
    if re.search(r"\d", kw):
        return None
    return f"{kw}: {bullet}" if bullet else None


def _bullets_for_company(
    norm_key: str,
    *,
    prior: TailoredResumeOutput | None,
    parsed: ParsedResume | None,
    must_have_keywords: list[str] | None,
) -> tuple[list[str], str, str, str]:
    prior_entry = _prior_entry(prior, norm_key)
    parsed_entry = _parsed_entry(parsed, norm_key)

    bullets: list[str] = []
    if prior_entry and prior_entry.bullets:
        bullets = [b.strip() for b in prior_entry.bullets if b.strip()]
    elif parsed_entry and parsed_entry.bullets:
        bullets = [b.strip() for b in parsed_entry.bullets if b.strip()]

    title = ""
    company = ""
    dates = ""
    if prior_entry and prior_entry.company:
        title = prior_entry.title or ""
        company = prior_entry.company
        dates = prior_entry.dates or ""
    elif parsed_entry and parsed_entry.company:
        title = parsed_entry.title or ""
        company = parsed_entry.company
        dates = parsed_entry.dates or ""

    if bullets and must_have_keywords:
        adjusted: list[str] = []
        for bullet in bullets:
            updated = bullet
            for kw in must_have_keywords:
                candidate = _absorb_keyword(updated, kw)
                if candidate:
                    updated = candidate
                    break
            adjusted.append(updated)
        bullets = adjusted

    return bullets, title, company, dates


def apply_experience_fallback(
    output: TailoredResumeOutput,
    *,
    resume_parsed: ParsedResume | None,
    phase2_output: AuditOutput | None,
    prior_output: TailoredResumeOutput | None,
    must_have_keywords: list[str] | None,
) -> TailoredResumeOutput:
    del phase2_output  # reserved for future section-scoped hints
    if not phase3_is_hollow(output):
        return output

    experience: list[TailoredExperienceEntry] = []
    for norm_key in _company_keys(resume_parsed, prior_output):
        bullets, title, company, dates = _bullets_for_company(
            norm_key,
            prior=prior_output,
            parsed=resume_parsed,
            must_have_keywords=must_have_keywords,
        )
        if not bullets:
            continue
        experience.append(
            TailoredExperienceEntry(
                title=title,
                company=company,
                dates=dates,
                bullets=bullets,
            )
        )

    notes = list(output.rewrite_notes)
    if _FALLBACK_NOTE not in notes:
        notes.append(_FALLBACK_NOTE)

    return output.model_copy(update={"experience": experience, "rewrite_notes": notes})


__all__ = ["apply_experience_fallback"]
