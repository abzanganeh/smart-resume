"""HTML → plain-text converter used when JD URLs return raw HTML pages.

Uses only stdlib (html.parser) — no extra dependencies.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser


# ── HTML tag stripper ────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Extract human-readable text from HTML, skipping script/style/head."""

    _SKIP = frozenset({"script", "style", "head", "meta", "link", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _looks_like_html(text: str) -> bool:
    """Return True if text appears to be an HTML document."""
    t = text.lstrip()[:200].lower()
    return t.startswith("<!doctype") or t.startswith("<html") or "<head" in t


def _extract_next_data(html: str) -> str | None:
    """Pull job-description text from Next.js __NEXT_DATA__ JSON if present.

    Many modern job boards (Jobright, Greenhouse, etc.) embed structured data
    in a <script id="__NEXT_DATA__"> block even when the page is JS-rendered.
    """
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (ValueError, KeyError):
        return None

    # Flatten all string leaves; collect anything ≥ 60 chars (a full sentence)
    parts: list[str] = []

    def _walk(obj: object) -> None:
        if isinstance(obj, str) and len(obj) >= 60:
            parts.append(obj.strip())
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return "\n".join(parts) if parts else None


def strip_html_to_text(raw: str, max_chars: int = 60_000) -> str:
    """Convert an HTML page to plain text suitable for LLM consumption.

    Strategy (in order):
    1. If text doesn't look like HTML, return it unchanged.
    2. Try to extract Next.js __NEXT_DATA__ JSON (richer, structured).
    3. Fall back to tag-stripping the full HTML.
    4. Collapse excessive blank lines.
    5. Trim to max_chars.
    """
    if not _looks_like_html(raw):
        return raw[:max_chars]

    # 1 — try __NEXT_DATA__ first (most accurate for JS-rendered job boards)
    next_text = _extract_next_data(raw)
    if next_text and len(next_text) >= 200:
        text = next_text
    else:
        # 2 — fall back to full HTML tag stripping
        extractor = _TextExtractor()
        extractor.feed(raw)
        text = extractor.get_text()

    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]
