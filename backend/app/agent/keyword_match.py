"""Shared deterministic keyword matching for Phase 1 presence and Phase 4 scoring."""

from __future__ import annotations

import re
from typing import Literal

_QUALIFIERS = re.compile(
    r"^(?:proficient\s+in|experience\s+(?:in|with|designing(?:\s+and\s+developing)?)?|"
    r"experienced?\s+(?:in|with)|knowledge\s+of|familiarity\s+with|skilled\s+in|"
    r"expertise\s+in|strong\s+background\s+in|ability\s+to|strong\s+|"
    r"\d+\+\s*years?\s+(?:of\s+)?(?:working\s+)?(?:with\s+)?)\s*",
    re.I,
)

_STOPWORDS = frozenset(
    {
        "in",
        "with",
        "of",
        "and",
        "the",
        "a",
        "an",
        "for",
        "to",
        "on",
        "at",
        "by",
        "such",
        "as",
        "is",
        "are",
        "be",
        "via",
        "using",
        "including",
        "or",
    }
)

_ABBREV = {
    "oo": "object-oriented",
    "oop": "object-oriented programming",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "aws": "amazon aws",
    "k8s": "kubernetes",
    "ts": "typescript",
    "js": "javascript",
}

_SOFT_SKILL_MARKERS = (
    "communication",
    "collaboration",
    "team player",
    "self-starter",
    "fast learner",
    "attention to detail",
    "problem solving",
    "engineering foundation",
    "written communication",
    "high agency",
    "ownership",
    "startup pace",
)

_SPLIT_PATTERN = re.compile(r"\s+and\s+|,|/|&", re.I)
_YEARS_PREFIX = re.compile(r"^\d+\+?\s*years?\s+", re.I)


def normalize_haystack(text: str) -> str:
    return (text or "").lower().replace("-", " ")


def is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch in {"+", "#"}


def contains_token(haystack: str, needle: str) -> bool:
    """Whole-token match; avoids Java matching inside JavaScript."""
    if not needle or not haystack:
        return False
    hay = normalize_haystack(haystack)
    term = needle.lower().strip()
    if not term:
        return False
    start = 0
    while True:
        idx = hay.find(term, start)
        if idx < 0:
            return False
        before = hay[idx - 1] if idx > 0 else " "
        after_idx = idx + len(term)
        after = hay[after_idx] if after_idx < len(hay) else " "
        if not is_word_char(before) and not is_word_char(after):
            return True
        start = idx + 1


def atomize_phrase(term: str) -> list[str]:
    cleaned = (term or "").strip()
    if not cleaned:
        return []
    if _YEARS_PREFIX.match(cleaned):
        return []
    if classify_scoring_tier(cleaned) == "context":
        return []

    core = _QUALIFIERS.sub("", cleaned).strip()
    source = core or cleaned
    parts = [p.strip() for p in _SPLIT_PATTERN.split(source) if p.strip()]
    if len(parts) <= 1:
        return [source] if source else []

    atoms: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part_core = _QUALIFIERS.sub("", part).strip()
        if not part_core or part_core.lower() in _STOPWORDS:
            continue
        if len(part_core) <= 2 and part_core.lower() not in _ABBREV:
            continue
        key = part_core.lower()
        if key in seen:
            continue
        seen.add(key)
        atoms.append(part_core)
    return atoms[:6] if atoms else [source]


def classify_scoring_tier(term: str) -> Literal["atomic", "context"]:
    t = (term or "").strip().lower()
    if not t:
        return "context"
    if _YEARS_PREFIX.match(t):
        return "context"
    if len(t) > 80:
        return "context"
    if any(marker in t for marker in _SOFT_SKILL_MARKERS):
        return "context"
    words = [w for w in re.split(r"\W+", t) if w]
    if len(words) >= 5 and not _looks_technical(t):
        return "context"
    return "atomic"


def _looks_technical(term: str) -> bool:
    t = term.lower()
    tech_tokens = (
        "python",
        "java",
        "typescript",
        "javascript",
        "kubernetes",
        "docker",
        "aws",
        "sql",
        "go",
        "rust",
        "c++",
        "llm",
        "api",
        "ci/cd",
        "siem",
        "oauth",
        "grpc",
    )
    return any(tok in t for tok in tech_tokens)


def _try_abbrev(term: str, hay: str) -> bool:
    for abbrev, full in _ABBREV.items():
        if re.search(r"\b" + re.escape(abbrev) + r"\b", term):
            candidate = re.sub(
                r"\b" + re.escape(abbrev) + r"\b",
                full,
                term,
            )
            candidate = re.sub(r"\s+", " ", candidate).strip()
            if candidate and contains_token(hay, candidate):
                return True
    return False


def string_present(term: str, resume_text: str) -> bool:
    """Heuristic presence check against raw resume text."""
    hay = normalize_haystack(resume_text)
    t = (term or "").strip().lower()
    if not t:
        return False
    if _YEARS_PREFIX.match(t):
        return False
    if contains_token(hay, t):
        return True
    if _try_abbrev(t, hay):
        return True

    core = _QUALIFIERS.sub("", t).strip()
    if core and core != t:
        if contains_token(hay, core) or _try_abbrev(core, hay):
            return True

    words = [w for w in re.split(r"\W+", core or t) if len(w) > 2 and w not in _STOPWORDS]
    if len(words) >= 2 and all(contains_token(hay, w) for w in words):
        return True
    if len(words) == 1 and contains_token(hay, words[0]):
        return True
    return False


def keyword_present_in_section(term: str, section_text: str) -> bool:
    return string_present(term, section_text)


def sections_with_keyword(term: str, sections: dict[str, str]) -> list[str]:
    present: list[str] = []
    for name, text in sections.items():
        if keyword_present_in_section(term, text):
            present.append(name)
    return present
