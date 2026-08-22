"""Hacker News \"Who is Hiring\" threads via Algolia search."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.services.career_watch.aggregators.sync import stable_external_id
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob

HN_ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_ALGOLIA_ITEMS_URL = "https://hn.algolia.com/api/v1/items/{story_id}"

# Typical line: "Company | Role | Location | ..."
_LINE_RE = re.compile(
    r"^(?P<company>[^|]+)\|\s*(?P<title>[^|]+)\|\s*(?P<location>[^|]+)",
)


def _parse_comment_lines(comment_text: str, *, thread_id: str) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for idx, line in enumerate(comment_text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        match = _LINE_RE.match(stripped)
        if not match:
            continue
        company = match.group("company").strip()
        title = match.group("title").strip()
        location = match.group("location").strip()
        if not company or not title:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=stable_external_id(
                    "hn_whos_hiring",
                    thread_id,
                    str(idx),
                    company,
                    title,
                ),
                title=title,
                location=location,
                apply_url=f"https://news.ycombinator.com/item?id={thread_id}",
                description_text=stripped,
                posted_at=None,
                raw_payload={
                    "company": company,
                    "hn_thread_id": thread_id,
                    "line": stripped,
                },
            )
        )
    return parsed


def parse_hn_thread_comments(
    thread_payload: dict[str, Any],
    *,
    thread_id: str,
) -> list[ParsedJob]:
    children = thread_payload.get("children") or []
    if not isinstance(children, list):
        return []
    jobs: list[ParsedJob] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        text = str(child.get("text") or child.get("comment_text") or "")
        if not text.strip():
            continue
        jobs.extend(_parse_comment_lines(text, thread_id=thread_id))
    return jobs


def parse_hn_search_payload(payload: dict[str, Any]) -> str | None:
    hits = payload.get("hits") or []
    if not isinstance(hits, list) or not hits:
        return None
    first = hits[0]
    if not isinstance(first, dict):
        return None
    story_id = str(first.get("objectID") or first.get("story_id") or "")
    return story_id or None


async def fetch_hn_whos_hiring_jobs(*, client: httpx.AsyncClient) -> list[ParsedJob]:
    search_payload = await fetch_json(
        client,
        HN_ALGOLIA_SEARCH_URL,
        params={
            "query": "Ask HN: Who is hiring",
            "tags": "story",
            "hitsPerPage": "1",
        },
    )
    if not isinstance(search_payload, dict):
        return []
    story_id = parse_hn_search_payload(search_payload)
    if not story_id:
        return []
    thread_payload = await fetch_json(
        client,
        HN_ALGOLIA_ITEMS_URL.format(story_id=story_id),
    )
    if not isinstance(thread_payload, dict):
        return []
    return parse_hn_thread_comments(thread_payload, thread_id=story_id)


__all__ = [
    "HN_ALGOLIA_ITEMS_URL",
    "HN_ALGOLIA_SEARCH_URL",
    "fetch_hn_whos_hiring_jobs",
    "parse_hn_search_payload",
    "parse_hn_thread_comments",
]
