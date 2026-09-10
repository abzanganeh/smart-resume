"""Normalize contact URLs extracted from resumes."""

from __future__ import annotations

import re

_LABEL_ONLY = {
    "linkedin": re.compile(r"^(linked\s*in|linkedin\.?)$", re.IGNORECASE),
    "github": re.compile(r"^(git\s*hub|github\.?)$", re.IGNORECASE),
}


def sanitize_contact_url(kind: str, value: str | None) -> str | None:
    """Return a usable URL, or None when the value is only a label."""
    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    if re.match(r"^(javascript|data|file|vbscript):", trimmed, re.IGNORECASE):
        return None

    pattern = _LABEL_ONLY.get(kind)
    if pattern and pattern.match(trimmed):
        return None

    if re.match(r"^https?://", trimmed, re.IGNORECASE):
        return trimmed

    if kind == "linkedin" and "linkedin.com" in trimmed.lower():
        return trimmed if trimmed.lower().startswith("http") else f"https://{trimmed}"

    if kind == "github" and "github.com" in trimmed.lower():
        return trimmed if trimmed.lower().startswith("http") else f"https://{trimmed}"

    if kind == "github" and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})?", trimmed):
        return f"https://github.com/{trimmed}"

    if pattern and not re.search(r"[./@]", trimmed):
        return None

    return None
