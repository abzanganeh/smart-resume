"""Remotive public remote jobs API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.services.career_watch.aggregators.sync import stable_external_id
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


def _parse_posted_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_remotive_payload(jobs_raw: list[dict[str, Any]]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("id") or "")
        title = str(item.get("title") or "").strip()
        if not job_id or not title:
            continue
        company = str(item.get("company_name") or "").strip()
        parsed.append(
            ParsedJob(
                external_job_id=stable_external_id("remotive", job_id),
                title=title,
                location=str(item.get("candidate_required_location") or ""),
                apply_url=str(item.get("url") or ""),
                description_text=str(item.get("description") or ""),
                posted_at=_parse_posted_at(item.get("publication_date")),
                raw_payload={**item, "company": company},
            )
        )
    return parsed


async def fetch_remotive_jobs(*, client: httpx.AsyncClient) -> list[ParsedJob]:
    payload = await fetch_json(client, REMOTIVE_API_URL)
    if not isinstance(payload, dict):
        return []
    jobs_raw = payload.get("jobs") or []
    if not isinstance(jobs_raw, list):
        return []
    return parse_remotive_payload(jobs_raw)


__all__ = ["REMOTIVE_API_URL", "fetch_remotive_jobs", "parse_remotive_payload"]
