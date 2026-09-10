"""Fetch job descriptions from URLs with ATS-specific adapters."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.brand import PRODUCT_NAME
from app.parsers.html_parser import strip_html_to_text

_LEVER_POSTING_URL = re.compile(
    r"^https?://(?:www\.)?jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})(?:[/?#].*)?$",
    re.IGNORECASE,
)
_LOGO_LINE = re.compile(r"\blogo\b", re.IGNORECASE)
_BOILERPLATE_PREFIXES = (
    "apply for this job",
    "jobs powered by",
    "home page",
    "salary:",
)
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google",
    }
)


@dataclass(frozen=True)
class FetchedJD:
    text: str
    title: str | None = None


def assert_safe_fetch_url(url: str) -> None:
    """Reject URLs that could reach private networks or cloud metadata."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("JD URL must be http(s)")
    host = parsed.hostname
    if not host:
        raise ValueError("JD URL must include a host")
    if host.lower() in _BLOCKED_HOSTNAMES or host.endswith(".local"):
        raise ValueError("JD URL host is not allowed")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError("JD URL host could not be resolved") from exc
    for info in addr_infos:
        ip = info[4][0]
        addr = ipaddress.ip_address(ip)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        ):
            raise ValueError("JD URL points to a private or restricted address")


async def _validate_request(request: httpx.Request) -> None:
    assert_safe_fetch_url(str(request.url))


def parse_lever_posting_url(url: str) -> tuple[str, str] | None:
    """Return (board_token, posting_id) for a Lever job URL."""
    cleaned = url.strip()
    if not cleaned:
        return None
    match = _LEVER_POSTING_URL.match(cleaned)
    if not match:
        return None
    return match.group(1), match.group(2)


def infer_jd_title_from_text(text: str) -> str | None:
    """Best-effort job title from plain JD text (skip logos and nav chrome)."""
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or len(candidate) > 120:
            continue
        lower = candidate.lower()
        if _LOGO_LINE.search(candidate):
            continue
        if any(lower.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
            continue
        if "|" in candidate and len(candidate) > 80:
            continue
        return candidate
    return None


def _ensure_title_leads(text: str, title: str | None) -> tuple[str, str | None]:
    """Prepend a detected title when scraped text starts with junk (e.g. alt text)."""
    if not text.strip():
        return text, title

    resolved_title = (title or "").strip() or infer_jd_title_from_text(text)
    if not resolved_title:
        return text, None

    first_line = text.strip().split("\n", 1)[0].strip()
    if first_line.lower() == resolved_title.lower():
        return text, resolved_title

    junk_first_line = (
        _LOGO_LINE.search(first_line)
        or len(first_line) < 4
        or any(first_line.lower().startswith(prefix) for prefix in _BOILERPLATE_PREFIXES)
    )
    if junk_first_line:
        return f"{resolved_title}\n\n{text.strip()}", resolved_title

    return text, resolved_title


async def _fetch_lever_posting(
    client: httpx.AsyncClient,
    board: str,
    posting_id: str,
) -> FetchedJD | None:
    api_url = f"https://api.lever.co/v0/postings/{board}/{posting_id}"
    resp = await client.get(
        api_url,
        headers={"User-Agent": f"Mozilla/5.0 (compatible; {PRODUCT_NAME}/1.0)"},
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    if not isinstance(data, dict):
        return None

    title = str(data.get("text") or "").strip() or None
    description = str(
        data.get("descriptionPlain") or data.get("description") or ""
    ).strip()
    if not description:
        return None

    text = f"{title}\n\n{description}" if title else description
    return FetchedJD(text=text, title=title)


async def fetch_jd_from_url(url: str, *, max_chars: int) -> FetchedJD:
    """Fetch JD text from a job-board URL."""
    cleaned_url = url.strip()
    if not cleaned_url:
        raise ValueError("JD URL is empty")

    parsed = urlparse(cleaned_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("JD URL must be http(s)")

    assert_safe_fetch_url(cleaned_url)

    headers = {"User-Agent": f"Mozilla/5.0 (compatible; {PRODUCT_NAME}/1.0)"}

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        event_hooks={"request": [_validate_request]},
    ) as client:
        lever_parts = parse_lever_posting_url(cleaned_url)
        if lever_parts:
            board, posting_id = lever_parts
            lever_jd = await _fetch_lever_posting(client, board, posting_id)
            if lever_jd and lever_jd.text.strip():
                text = lever_jd.text[:max_chars]
                return FetchedJD(text=text, title=lever_jd.title)

        resp = await client.get(cleaned_url, headers=headers)
        resp.raise_for_status()
        text = strip_html_to_text(resp.text, max_chars=max_chars)

    text, title = _ensure_title_leads(text, None)
    return FetchedJD(text=text[:max_chars], title=title)
