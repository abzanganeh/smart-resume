"""Generic HTML careers page adapter."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_text
from app.services.career_watch.types import ParsedJob

_JOB_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>[^<]{4,120})</a>',
    re.IGNORECASE,
)
_JOB_KEYWORDS = (
    "job",
    "career",
    "position",
    "opening",
    "role",
    "apply",
    "opportunity",
)


def _looks_like_job_link(href: str, title: str) -> bool:
    combined = f"{href} {title}".lower()
    return any(word in combined for word in _JOB_KEYWORDS)


def _external_id(href: str, title: str) -> str:
    digest = hashlib.sha256(f"{href}|{title}".encode()).hexdigest()
    return digest[:32]


class GenericHtmlAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        html = await fetch_text(client, company.careers_page_url, accept="text/html")
        return parse_generic_html(html, base_url=company.careers_page_url)


def parse_generic_html(html: str, *, base_url: str) -> list[ParsedJob]:
    """Heuristically extract job-like links from arbitrary HTML."""
    parsed: list[ParsedJob] = []
    seen: set[str] = set()
    base_host = urlparse(base_url).netloc

    for match in _JOB_ANCHOR_RE.finditer(html):
        href = match.group("href").strip()
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        if not href or not title or not _looks_like_job_link(href, title):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc and urlparse(absolute).netloc != base_host:
            continue
        key = absolute.lower()
        if key in seen:
            continue
        seen.add(key)
        parsed.append(
            ParsedJob(
                external_job_id=_external_id(absolute, title),
                title=title,
                location="",
                apply_url=absolute,
                description_text="",
                posted_at=None,
                raw_payload={"href": absolute, "title": title},
            )
        )
    return parsed


__all__ = ["GenericHtmlAdapter", "parse_generic_html"]
