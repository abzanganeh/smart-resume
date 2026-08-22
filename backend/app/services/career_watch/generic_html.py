"""Generic HTML careers page adapter."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_text
from app.services.career_watch.types import ParsedJob

_JOB_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>[^<]{4,120})</a>',
    re.IGNORECASE,
)
_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_JOB_KEYWORDS = (
    "job",
    "career",
    "position",
    "opening",
    "role",
    "apply",
    "opportunity",
)
_JOB_POSTING_TYPES = frozenset({"JobPosting", "jobposting"})


def _strip_html(value: str) -> str:
    return unescape(_TAG_RE.sub(" ", value or "")).strip()


def _parse_posted_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _looks_like_job_link(href: str, title: str) -> bool:
    combined = f"{href} {title}".lower()
    return any(word in combined for word in _JOB_KEYWORDS)


def _external_id(href: str, title: str) -> str:
    digest = hashlib.sha256(f"{href}|{title}".encode()).hexdigest()
    return digest[:32]


def _is_job_posting(node: dict[str, Any]) -> bool:
    raw_type = node.get("@type")
    if isinstance(raw_type, str):
        return raw_type.casefold() in _JOB_POSTING_TYPES
    if isinstance(raw_type, list):
        return any(
            isinstance(item, str) and item.casefold() in _JOB_POSTING_TYPES
            for item in raw_type
        )
    return False


def _iter_jsonld_nodes(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if _is_job_posting(payload):
            return [payload]
        graph = payload.get("@graph")
        if isinstance(graph, list):
            nodes: list[dict[str, Any]] = []
            for item in graph:
                nodes.extend(_iter_jsonld_nodes(item))
            return nodes
        return []
    if isinstance(payload, list):
        nodes: list[dict[str, Any]] = []
        for item in payload:
            nodes.extend(_iter_jsonld_nodes(item))
        return nodes
    return []


def _location_from_job_posting(node: dict[str, Any]) -> str:
    location = node.get("jobLocation")
    if isinstance(location, str):
        return location.strip()
    if isinstance(location, list):
        parts = [_location_from_job_posting({"jobLocation": item}) for item in location]
        return "; ".join(part for part in parts if part)
    if isinstance(location, dict):
        address = location.get("address")
        if isinstance(address, dict):
            bits = [
                str(address.get(key) or "").strip()
                for key in ("addressLocality", "addressRegion", "addressCountry")
            ]
            joined = ", ".join(bit for bit in bits if bit)
            if joined:
                return joined
        name = location.get("name")
        if isinstance(name, str):
            return name.strip()
    return ""


def _apply_url_from_job_posting(node: dict[str, Any], *, base_url: str) -> str:
    for key in ("url", "sameAs", "directApply"):
        raw = node.get(key)
        if isinstance(raw, str) and raw.strip():
            return urljoin(base_url, raw.strip())
    identifier = node.get("identifier")
    if isinstance(identifier, dict):
        value = identifier.get("value") or identifier.get("@id")
        if isinstance(value, str) and value.strip():
            if value.startswith("http"):
                return value.strip()
            return urljoin(base_url, value.strip())
    return base_url


def _title_from_job_posting(node: dict[str, Any]) -> str:
    for key in ("title", "name"):
        raw = node.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "Untitled"


def _description_from_job_posting(node: dict[str, Any]) -> str:
    raw = node.get("description")
    if isinstance(raw, str):
        return _strip_html(raw)
    return ""


def _external_id_from_job_posting(
    node: dict[str, Any], *, apply_url: str, title: str
) -> str:
    identifier = node.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip()[:64]
    if isinstance(identifier, dict):
        value = identifier.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()[:64]
    return _external_id(apply_url, title)


def parse_jsonld_job_postings(html: str, *, base_url: str) -> list[ParsedJob]:
    """Extract schema.org ``JobPosting`` rows from JSON-LD script blocks."""
    parsed: list[ParsedJob] = []
    seen: set[str] = set()

    for match in _JSONLD_SCRIPT_RE.finditer(html):
        body = match.group("body").strip()
        if not body:
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue

        for node in _iter_jsonld_nodes(payload):
            title = _title_from_job_posting(node)
            apply_url = _apply_url_from_job_posting(node, base_url=base_url)
            key = apply_url.lower()
            if key in seen:
                continue
            seen.add(key)
            parsed.append(
                ParsedJob(
                    external_job_id=_external_id_from_job_posting(
                        node, apply_url=apply_url, title=title
                    ),
                    title=title,
                    location=_location_from_job_posting(node),
                    apply_url=apply_url,
                    description_text=_description_from_job_posting(node),
                    posted_at=_parse_posted_at(node.get("datePosted")),
                    raw_payload=node,
                )
            )
    return parsed


class GenericHtmlAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        html = await fetch_text(client, company.careers_page_url, accept="text/html")
        return parse_generic_html(html, base_url=company.careers_page_url)


def _parse_anchor_jobs(html: str, *, base_url: str) -> list[ParsedJob]:
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


def parse_generic_html(html: str, *, base_url: str) -> list[ParsedJob]:
    """Extract jobs from JSON-LD ``JobPosting`` blocks, else job-like links."""
    jsonld_jobs = parse_jsonld_job_postings(html, base_url=base_url)
    if jsonld_jobs:
        return jsonld_jobs
    return _parse_anchor_jobs(html, base_url=base_url)


__all__ = [
    "GenericHtmlAdapter",
    "parse_generic_html",
    "parse_jsonld_job_postings",
]
