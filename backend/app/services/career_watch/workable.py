"""Workable public widget API adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_api_url(slug: str) -> str:
    return f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"


def _location_name(location: object) -> str:
    if isinstance(location, dict):
        return str(location.get("location_str") or location.get("city") or "")
    return str(location or "")


def parse_workable_payload(jobs_raw: list[dict[str, Any]]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("shortcode") or item.get("id") or "")
        if not job_id:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("title") or "Untitled"),
                location=_location_name(item.get("location")),
                apply_url=str(item.get("url") or item.get("shortlink") or ""),
                description_text=str(item.get("description") or ""),
                posted_at=_parse_posted_at(str(item.get("published") or "") or None),
                raw_payload=item,
            )
        )
    return parsed


class WorkableAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        slug = company.ats_board_token
        if not slug:
            raise ValueError("workable adapter requires ats_board_token")

        payload = await fetch_json(client, _build_api_url(slug))
        if not isinstance(payload, dict):
            return []
        jobs_raw = payload.get("jobs") or []
        if not isinstance(jobs_raw, list):
            return []
        return parse_workable_payload(jobs_raw)


__all__ = ["WorkableAdapter", "parse_workable_payload"]
