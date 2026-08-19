"""Deterministic verification hints for story-generated resumes.

Compares spoken segment text against the generated resume draft so the
user can double-check names and dates before saving to their profile.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

VerifyStatus = Literal["ok", "review"]

_EXPERIENCE_LINE = re.compile(
    r"^(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$",
    re.MULTILINE,
)
_MONTH_YEAR = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{4}\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_AT_COMPANY = re.compile(
    r"\b(?:at|for|from)\s+([A-Za-z][A-Za-z0-9&\-. ]{2,40}?)(?:\s+(?:since|from|in|I|we|they|that|there|where|when|and|or)\b|[,.]|$)",
    re.IGNORECASE,
)
_CALLED_COMPANY = re.compile(
    r"\bcalled\s+([A-Za-z][A-Za-z0-9&\-. ]{2,40}?)(?:\s+(?:in|I|it|that|there|where|and|or)\b|[,.]|$)",
    re.IGNORECASE,
)
_SCHOOL = re.compile(
    r"\b(University of [A-Za-z ]+|Portland Community College|[A-Za-z ]+ University)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class VerifyItem:
    field: str
    spoken: str
    resume: str
    status: VerifyStatus
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _normalize(text)) if len(t) > 2}


def _names_match(spoken: str, resume: str) -> bool:
    s, r = _normalize(spoken), _normalize(resume)
    if s == r or s in r or r in s:
        return True
    s_tok, r_tok = _tokens(spoken), _tokens(resume)
    if not s_tok or not r_tok:
        return False
    overlap = len(s_tok & r_tok) / max(len(s_tok), len(r_tok))
    return overlap >= 0.6


def _extract_experience_block(resume_text: str) -> str:
    upper = resume_text.upper()
    start = upper.find("EXPERIENCE")
    if start < 0:
        return resume_text
    end_candidates = [
        upper.find(h, start + 1)
        for h in ("EDUCATION", "PROJECTS", "CERTIFICATIONS", "SKILLS")
        if upper.find(h, start + 1) >= 0
    ]
    end = min(end_candidates) if end_candidates else len(resume_text)
    return resume_text[start:end]


def extract_resume_companies(resume_text: str) -> list[tuple[str, str, str]]:
    block = _extract_experience_block(resume_text)
    entries: list[tuple[str, str, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.upper() == "EXPERIENCE" or line.startswith("•"):
            continue
        m = _EXPERIENCE_LINE.match(line)
        if m:
            entries.append((m.group(1).strip(), m.group(2).strip(), m.group(3).strip()))
    return entries


def extract_spoken_companies(segments: list[str]) -> list[str]:
    text = " ".join(segments)
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (_AT_COMPANY, _CALLED_COMPANY):
        for m in pattern.finditer(text):
            name = m.group(1).strip(" .,")
            key = _normalize(name)
            if len(key) < 3 or key in seen:
                continue
            seen.add(key)
            found.append(name)
    for m in _SCHOOL.finditer(text):
        name = m.group(1).strip()
        key = _normalize(name)
        if key not in seen:
            seen.add(key)
            found.append(name)
    return found


def extract_spoken_date_phrases(segments: list[str]) -> list[str]:
    text = " ".join(segments)
    phrases: list[str] = []
    seen: set[str] = set()
    for m in _MONTH_YEAR.finditer(text):
        phrase = m.group(0)
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            phrases.append(phrase)
    for m in re.finditer(r"\b(summer|spring|fall|winter)\s+\d{4}\b", text, re.I):
        phrase = m.group(0)
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            phrases.append(phrase)
    for m in re.finditer(r"\b\d{4}\s*(?:to|–|-)\s*(?:\d{4}|present|now)\b", text, re.I):
        phrase = m.group(0)
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            phrases.append(phrase)
    return phrases


def extract_resume_date_phrases(resume_text: str) -> list[str]:
    block = _extract_experience_block(resume_text)
    phrases: list[str] = []
    seen: set[str] = set()
    for _, _, dates in extract_resume_companies(resume_text):
        key = dates.lower()
        if key not in seen:
            seen.add(key)
            phrases.append(dates)
    for m in _MONTH_YEAR.finditer(block):
        phrase = m.group(0)
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            phrases.append(phrase)
    for m in _YEAR.finditer(block):
        phrase = m.group(0)
        key = phrase.lower()
        if key not in seen and phrase not in phrases:
            seen.add(key)
            phrases.append(phrase)
    return phrases


def _company_review_message(spoken: str, resume: str) -> str:
    if " " in resume and " " not in spoken.replace(" ", ""):
        pass
    s_words = spoken.split()
    r_words = resume.split()
    if len(s_words) >= 2 and len(r_words) >= 2:
        if s_words[0].lower() == r_words[0].lower() and s_words[-1].lower() == r_words[-1].lower():
            return "Speech may have split this name — confirm spelling (e.g. BrightCart vs Bright Card)."
    if _normalize(spoken) != _normalize(resume):
        return "Confirm employer or project name spelling matches your records."
    return "Review this name."


def _dates_related(spoken: str, resume: str) -> bool:
    if _names_match(spoken, resume) or spoken.lower() in resume.lower() or resume.lower() in spoken.lower():
        return True
    spoken_years = set(_YEAR.findall(spoken))
    resume_years = set(_YEAR.findall(resume))
    return bool(spoken_years & resume_years)


def build_verify_items(segments: list[str], resume_text: str) -> list[VerifyItem]:
    items: list[VerifyItem] = []
    spoken_companies = extract_spoken_companies(segments)
    resume_entries = extract_resume_companies(resume_text)
    resume_companies = [c for c, _, _ in resume_entries]

    matched_resume: set[int] = set()
    for spoken in spoken_companies:
        best_idx = -1
        for i, resume_co in enumerate(resume_companies):
            if i in matched_resume:
                continue
            if _names_match(spoken, resume_co):
                best_idx = i
                break
        if best_idx >= 0:
            matched_resume.add(best_idx)
            resume_co = resume_companies[best_idx]
            if _normalize(spoken) == _normalize(resume_co):
                items.append(
                    VerifyItem(
                        field="Employer / organization",
                        spoken=spoken,
                        resume=resume_co,
                        status="ok",
                        message="Name matches your story.",
                    )
                )
            else:
                items.append(
                    VerifyItem(
                        field="Employer / organization",
                        spoken=spoken,
                        resume=resume_co,
                        status="review",
                        message=_company_review_message(spoken, resume_co),
                    )
                )
        else:
            items.append(
                VerifyItem(
                    field="Employer / organization",
                    spoken=spoken,
                    resume="(not found in resume)",
                    status="review",
                    message="Mentioned in your story but missing from Experience — add or remove.",
                )
            )

    for i, resume_co in enumerate(resume_companies):
        if i not in matched_resume:
            items.append(
                VerifyItem(
                    field="Employer / organization",
                    spoken="(not in story)",
                    resume=resume_co,
                    status="review",
                    message="In the resume but not clearly heard in your story — confirm it is correct.",
                )
            )

    spoken_dates = extract_spoken_date_phrases(segments)
    resume_dates = extract_resume_date_phrases(resume_text)
    for spoken_date in spoken_dates[:8]:
        matched = any(_dates_related(spoken_date, rd) for rd in resume_dates)
        if matched:
            resume_match = next(
                (rd for rd in resume_dates if _dates_related(spoken_date, rd)),
                spoken_date,
            )
            status: VerifyStatus = "ok"
            message = "Date aligns with your story."
            if re.search(r"\b(summer|spring|fall|winter)\b", spoken_date, re.I) and _MONTH_YEAR.search(resume_match):
                status = "review"
                message = "You said a season; resume uses a specific month — confirm the month is right."
            items.append(
                VerifyItem(
                    field="Dates",
                    spoken=spoken_date,
                    resume=resume_match,
                    status=status,
                    message=message,
                )
            )
        else:
            items.append(
                VerifyItem(
                    field="Dates",
                    spoken=spoken_date,
                    resume="(not matched)",
                    status="review",
                    message="Date from your story may be missing or changed in the resume.",
                )
            )

    return items
