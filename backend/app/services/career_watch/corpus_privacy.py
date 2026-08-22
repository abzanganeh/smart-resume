"""Strip user-scoped fields before writing polled jobs into shared ``job_cache``."""

from __future__ import annotations

from typing import Any

from app.services.career_watch.types import ParsedJob

# Keys that must never appear in shared corpus payloads or search-facing rows.
_USER_SCOPED_RAW_KEYS = frozenset(
    {
        "user_id",
        "user_watched_company_id",
        "watch_id",
        "keywords",
        "keyword_filters",
        "email",
        "alert_email",
    }
)

# Shared corpus source tags — never user- or watch-specific identifiers.
ALLOWED_CORPUS_SOURCES = frozenset({"corpus"})


def sanitize_raw_payload_for_corpus(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``raw`` with user-scoped keys removed."""
    return {key: value for key, value in raw.items() if key not in _USER_SCOPED_RAW_KEYS}


def sanitize_parsed_job_for_corpus(job: ParsedJob) -> ParsedJob:
    """Ensure ``ParsedJob`` is safe to upsert into the shared search corpus."""
    cleaned = sanitize_raw_payload_for_corpus(job.raw_payload)
    if cleaned is job.raw_payload:
        return job
    return ParsedJob(
        external_job_id=job.external_job_id,
        title=job.title,
        location=job.location,
        apply_url=job.apply_url,
        description_text=job.description_text,
        posted_at=job.posted_at,
        raw_payload=cleaned,
    )


def assert_corpus_sources(sources: list[str]) -> list[str]:
    """Reject source tags that could expose per-user watch state."""
    normalized: list[str] = []
    for source in sources:
        lowered = source.lower()
        if lowered.startswith("user:") or lowered.startswith("watch:"):
            continue
        normalized.append(source)
    return normalized


__all__ = [
    "ALLOWED_CORPUS_SOURCES",
    "assert_corpus_sources",
    "sanitize_parsed_job_for_corpus",
    "sanitize_raw_payload_for_corpus",
]
