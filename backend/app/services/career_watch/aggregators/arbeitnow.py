"""Arbeitnow public job board API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.services.career_watch.aggregators.sync import stable_external_id
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob

ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"


def _parse_posted_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_arbeitnow_payload(rows: list[dict[str, Any]]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        title = str(item.get("title") or "").strip()
        company = str(item.get("company_name") or "").strip()
        if not slug or not title:
            continue
        location = str(item.get("location") or "")
        parsed.append(
            ParsedJob(
                external_job_id=stable_external_id("arbeitnow", slug),
                title=title,
                location=location,
                apply_url=str(item.get("url") or ""),
                description_text=str(item.get("description") or ""),
                posted_at=_parse_posted_at(item.get("created_at")),
                raw_payload={
                    **item,
                    "company": company,
                    "remote": bool(item.get("remote")),
                },
            )
        )
    return parsed


async def fetch_arbeitnow_jobs(*, client: httpx.AsyncClient) -> list[ParsedJob]:
    payload = await fetch_json(client, ARBEITNOW_API_URL)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        return []
    return parse_arbeitnow_payload(rows)


__all__ = ["ARBEITNOW_API_URL", "fetch_arbeitnow_jobs", "parse_arbeitnow_payload"]
