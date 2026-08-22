"""RemoteOK public jobs API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.career_watch.aggregators.sync import stable_external_id
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob

REMOTEOK_API_URL = "https://remoteok.com/api"


def _parse_epoch(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    return None


def parse_remoteok_payload(rows: list[dict[str, Any]]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if "position" not in item and "company" not in item:
            continue
        slug = str(item.get("slug") or item.get("id") or "")
        title = str(item.get("position") or item.get("title") or "").strip()
        company = str(item.get("company") or "").strip()
        if not slug or not title:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=stable_external_id("remoteok", slug),
                title=title,
                location=str(item.get("location") or "Remote"),
                apply_url=str(item.get("url") or item.get("apply_url") or ""),
                description_text=str(item.get("description") or ""),
                posted_at=_parse_epoch(item.get("epoch") or item.get("date")),
                raw_payload={**item, "company": company, "remote": True},
            )
        )
    return parsed


async def fetch_remoteok_jobs(*, client: httpx.AsyncClient) -> list[ParsedJob]:
    payload = await fetch_json(client, REMOTEOK_API_URL)
    if not isinstance(payload, list):
        return []
    job_rows = [row for row in payload if isinstance(row, dict)]
    return parse_remoteok_payload(job_rows)


__all__ = ["REMOTEOK_API_URL", "fetch_remoteok_jobs", "parse_remoteok_payload"]
