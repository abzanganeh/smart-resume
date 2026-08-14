"""Workday careers page adapter (JSON embedded in HTML)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_text
from app.services.career_watch.types import ParsedJob

_EMBEDDED_JSON_RE = re.compile(
    r"window\.(?:workday|WD)\.(?:config|pageConfig)\s*=\s*(\{.*?\});",
    re.DOTALL,
)
_JOB_LINK_RE = re.compile(
    r'href="(/[^"]+/job/[^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class WorkdayAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        html = await fetch_text(client, company.careers_page_url, accept="text/html")
        return parse_workday_html(html, base_url=company.careers_page_url)


def parse_workday_html(html: str, *, base_url: str) -> list[ParsedJob]:
    """Extract job links from a Workday careers HTML page."""
    parsed: list[ParsedJob] = []
    seen: set[str] = set()

    for match in _JOB_LINK_RE.finditer(html):
        href, title = match.group(1), match.group(2).strip()
        if not title or href in seen:
            continue
        seen.add(href)
        job_id = href.rstrip("/").split("/")[-1]
        apply_url = href if href.startswith("http") else _join_url(base_url, href)
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=title,
                location="",
                apply_url=apply_url,
                description_text="",
                posted_at=None,
                raw_payload={"href": href, "title": title},
            )
        )

    if parsed:
        return parsed

    embedded = _EMBEDDED_JSON_RE.search(html)
    if embedded:
        try:
            config = json.loads(embedded.group(1))
        except json.JSONDecodeError:
            config = {}
        postings = config.get("postings") or config.get("jobs") or []
        if isinstance(postings, list):
            for item in postings:
                if not isinstance(item, dict):
                    continue
                job_id = str(item.get("externalPath") or item.get("bulletFields", [""])[0])
                if not job_id:
                    continue
                parsed.append(
                    ParsedJob(
                        external_job_id=job_id,
                        title=str(item.get("title") or "Untitled"),
                        location=str(item.get("location") or ""),
                        apply_url=str(item.get("externalUrl") or base_url),
                        description_text=str(item.get("description") or ""),
                        posted_at=_parse_posted_at(str(item.get("postedOn") or "") or None),
                        raw_payload=item,
                    )
                )
    return parsed


def _join_url(base: str, path: str) -> str:
    if path.startswith("http"):
        return path
    base = base.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


__all__ = ["WorkdayAdapter", "parse_workday_html"]
