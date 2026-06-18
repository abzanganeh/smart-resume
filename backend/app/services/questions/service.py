"""Load and query the curated interview question seed bank."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from app.services.questions.models import InterviewQuestion

log = structlog.get_logger()

_SEED_DIR = Path(__file__).resolve().parent / "seed"
_DEFAULT_LIMIT = 30
_MAX_LIMIT = 100

_DOMAIN_ALIASES: dict[str, str] = {
    "software engineering": "software_engineering",
    "software_engineer": "software_engineering",
    "swe": "software_engineering",
    "product management": "product_management",
    "finance": "finance",
    "marketing": "marketing",
    "sales": "sales",
    "operations": "operations",
}


def _normalize_domain(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return _DOMAIN_ALIASES.get(cleaned, slug)


def _normalize_optional(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    return cleaned or None


@lru_cache(maxsize=1)
def _load_bank() -> tuple[InterviewQuestion, ...]:
    entries: list[InterviewQuestion] = []
    for path in sorted(_SEED_DIR.glob("*.json")):
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("questions.seed_load_failed", path=str(path), error=str(exc))
            continue
        for item in payload.get("questions", []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            question_id = str(item.get("id") or "").strip()
            if not text or not question_id:
                continue
            entries.append(
                InterviewQuestion(
                    id=question_id,
                    text=text,
                    domain=str(item.get("domain") or payload.get("domain") or "universal"),
                    category=str(item.get("category") or "general"),
                    canonical_answer=item.get("canonical_answer"),
                )
            )
    log.info("questions.bank_loaded", count=len(entries), packs=len(list(_SEED_DIR.glob("*.json"))))
    return tuple(entries)


def _role_relevance_score(question: InterviewQuestion, role: str | None) -> int:
    if not role:
        return 0
    role_tokens = {t for t in re.split(r"[^a-z0-9]+", role.lower()) if len(t) > 2}
    if not role_tokens:
        return 0
    haystack = f"{question.text} {question.category}".lower()
    return sum(1 for token in role_tokens if token in haystack)


def list_interview_questions(
    *,
    domain: str | None = None,
    company: str | None = None,
    role: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[InterviewQuestion]:
    """Return universal questions plus domain-specific matches.

    Universal questions are always included first. Domain pack questions are
    appended when ``domain`` matches a seed pack. ``company`` is accepted for
    forward-compatible filtering but does not narrow results in the seed phase.
    ``role`` softly boosts ordering within the domain slice.
    """
    del company  # reserved for premium / company-specific packs (Phase 10.3+)

    normalized_domain = _normalize_domain(domain)
    normalized_role = _normalize_optional(role)
    clamped_limit = max(1, min(limit, _MAX_LIMIT))

    bank = list(_load_bank())
    universal = [q for q in bank if q.domain == "universal"]
    domain_specific: list[InterviewQuestion] = []
    if normalized_domain:
        domain_specific = [q for q in bank if q.domain == normalized_domain]

    if normalized_role and domain_specific:
        domain_specific.sort(
            key=lambda q: (_role_relevance_score(q, normalized_role), q.id),
            reverse=True,
        )

    merged: list[InterviewQuestion] = []
    seen: set[str] = set()
    for question in universal + domain_specific:
        if question.id in seen:
            continue
        seen.add(question.id)
        merged.append(question)
        if len(merged) >= clamped_limit:
            break

    return merged
