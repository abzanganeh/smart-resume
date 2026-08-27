"""Preferred job search titles stored on ``users.job_default_filters``.

Suggestions are generated once from the master resume and re-generated only
when the master resume text meaningfully changes (see
``compute_master_resume_hash`` and ``is_source_stale``).  Regeneration itself
is free — we don't charge a credit for it — but we rate-limit at the router
layer and gate regeneration on hash mismatch so callers can't spam the LLM.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from app.models.user import User

PREFERRED_TITLES_KEY = "preferred_titles"
PREFERRED_TITLES_CONFIRMED_AT_KEY = "preferred_titles_confirmed_at"
PREFERRED_TITLES_SOURCE_HASH_KEY = "preferred_titles_source_hash"

MIN_PREFERRED_JOB_TITLES = 1
MAX_PREFERRED_JOB_TITLES = 12
JOB_TITLE_SUGGESTION_COUNT = 10

_RESERVED_FILTER_KEYS = frozenset(
    {
        PREFERRED_TITLES_KEY,
        PREFERRED_TITLES_CONFIRMED_AT_KEY,
        PREFERRED_TITLES_SOURCE_HASH_KEY,
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def compute_master_resume_hash(raw_text: str | None) -> str:
    """Stable content hash over a normalized master-resume snapshot.

    Small edits (a whitespace tweak, trailing newline) do not invalidate
    suggestions; substantive rewrites do.  We normalize by lowercasing and
    collapsing whitespace before hashing so cosmetic changes are ignored.
    """
    normalized = _WHITESPACE_RE.sub(" ", (raw_text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def search_filters_from_user(user: User) -> dict[str, Any]:
    """Return job search filters only — excludes preferred-title metadata."""
    raw = dict(user.job_default_filters or {})
    for key in _RESERVED_FILTER_KEYS:
        raw.pop(key, None)
    return raw


def get_preferred_titles(user: User) -> list[str]:
    raw = (user.job_default_filters or {}).get(PREFERRED_TITLES_KEY) or []
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        title = item.strip()
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(title[:200])
    return out


def has_confirmed_preferred_titles(user: User) -> bool:
    return len(get_preferred_titles(user)) >= MIN_PREFERRED_JOB_TITLES


def get_preferred_titles_source_hash(user: User) -> str | None:
    raw = (user.job_default_filters or {}).get(PREFERRED_TITLES_SOURCE_HASH_KEY)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def is_source_stale(user: User, *, current_hash: str | None) -> bool:
    """True when the user has confirmed titles but the source hash no longer matches.

    A missing stored hash on an already-confirmed user is treated as stale so
    we prompt for a one-time regeneration after this feature rolls out.
    """
    if not has_confirmed_preferred_titles(user):
        return False
    stored = get_preferred_titles_source_hash(user)
    if not current_hash:
        return False
    if stored is None:
        return True
    return stored != current_hash


def set_preferred_titles(
    user: User,
    titles: list[str],
    *,
    source_hash: str | None = None,
) -> list[str]:
    """Normalize, dedupe, and persist preferred titles on the user row.

    Pass ``source_hash`` (from :func:`compute_master_resume_hash`) so we
    can detect when the master resume has meaningfully changed and suggest
    a free regeneration.
    """
    seen: set[str] = set()
    normalized: list[str] = []
    for item in titles:
        title = (item or "").strip()
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(title[:200])
        if len(normalized) >= MAX_PREFERRED_JOB_TITLES:
            break

    filters = dict(user.job_default_filters or {})
    filters[PREFERRED_TITLES_KEY] = normalized
    if len(normalized) >= MIN_PREFERRED_JOB_TITLES:
        filters[PREFERRED_TITLES_CONFIRMED_AT_KEY] = datetime.now(
            timezone.utc
        ).isoformat()
        if source_hash:
            filters[PREFERRED_TITLES_SOURCE_HASH_KEY] = source_hash
    else:
        filters.pop(PREFERRED_TITLES_CONFIRMED_AT_KEY, None)
        filters.pop(PREFERRED_TITLES_SOURCE_HASH_KEY, None)
    user.job_default_filters = filters
    return normalized
