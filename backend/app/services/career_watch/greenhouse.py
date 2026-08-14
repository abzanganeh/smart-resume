"""Greenhouse public boards API adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    return unescape(_TAG_RE.sub(" ", value or "")).strip()


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_api_url(board_token: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"


class GreenhouseAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        token = company.ats_board_token
        if not token:
            raise ValueError("greenhouse adapter requires ats_board_token")

        payload = await fetch_json(client, _build_api_url(token))
        jobs_raw = payload.get("jobs", []) if isinstance(payload, dict) else []
        parsed: list[ParsedJob] = []
        for item in jobs_raw:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "")
            if not job_id:
                continue
            location = ""
            loc = item.get("location")
            if isinstance(loc, dict):
                location = str(loc.get("name") or "")
            elif isinstance(loc, str):
                location = loc
            absolute_url = str(item.get("absolute_url") or company.careers_page_url)
            content = _strip_html(str(item.get("content") or ""))
            parsed.append(
                ParsedJob(
                    external_job_id=job_id,
                    title=str(item.get("title") or "Untitled"),
                    location=location,
                    apply_url=absolute_url,
                    description_text=content,
                    posted_at=_parse_posted_at(
                        str(item.get("updated_at") or item.get("created_at") or "")
                        or None
                    ),
                    raw_payload=item,
                )
            )
        return parsed


def parse_greenhouse_payload(jobs_raw: list[dict[str, Any]]) -> list[ParsedJob]:
    """Parse a Greenhouse jobs list without network I/O (tests)."""
    adapter = GreenhouseAdapter()
    company = WatchedCompany(
        name="Test",
        slug="test",
        careers_page_url="https://boards.greenhouse.io/test",
        ats_board_token="test",
    )
    parsed: list[ParsedJob] = []
    for item in jobs_raw:
        job_id = str(item.get("id") or "")
        if not job_id:
            continue
        location = ""
        loc = item.get("location")
        if isinstance(loc, dict):
            location = str(loc.get("name") or "")
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("title") or "Untitled"),
                location=location,
                apply_url=str(item.get("absolute_url") or ""),
                description_text=_strip_html(str(item.get("content") or "")),
                posted_at=_parse_posted_at(
                    str(item.get("updated_at") or item.get("created_at") or "") or None
                ),
                raw_payload=item,
            )
        )
    return parsed


__all__ = ["GreenhouseAdapter", "parse_greenhouse_payload"]
