"""Server-side filtering for job search results (§18.10 blocked companies)."""

from __future__ import annotations

from app.services.jobs.schemas import JobResult


def normalize_company_name(name: str) -> str:
    return name.strip().lower()


def filter_blocked_companies(
    jobs: list[JobResult],
    blocked_companies: list[str] | None,
) -> list[JobResult]:
    """Remove jobs whose company matches a user blocklist (case-insensitive)."""
    if not blocked_companies:
        return jobs
    blocked = {normalize_company_name(c) for c in blocked_companies if c and c.strip()}
    if not blocked:
        return jobs
    return [
        job
        for job in jobs
        if normalize_company_name(job.company) not in blocked
    ]


__all__ = ["filter_blocked_companies", "normalize_company_name"]
