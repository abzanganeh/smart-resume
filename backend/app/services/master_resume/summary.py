"""Human-readable master resume summaries for dashboard activity (not chunk_count)."""

from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def summarize_parsed_sections(parsed_sections: dict[str, Any] | None) -> str | None:
    """Roles / schools / projects copy for activity feed and API consumers."""
    if not parsed_sections:
        return None

    parts: list[str] = []

    roles = len(_as_list(parsed_sections.get("experience")))
    if roles:
        parts.append(f"{roles} role{'s' if roles != 1 else ''}")

    schools = len(_as_list(parsed_sections.get("education")))
    if schools:
        parts.append(f"{schools} school{'s' if schools != 1 else ''}")

    projects = len(_as_list(parsed_sections.get("project")))
    if projects:
        parts.append(f"{projects} project{'s' if projects != 1 else ''}")

    certs = len(_as_list(parsed_sections.get("cert")))
    if certs:
        parts.append(f"{certs} cert{'s' if certs != 1 else ''}")

    if parts:
        return " · ".join(parts[:3])

    sections = 0
    summary = parsed_sections.get("summary")
    if isinstance(summary, str) and summary.strip():
        sections += 1
    if _as_list(parsed_sections.get("skills")):
        sections += 1
    for key in ("publication", "award", "patent", "language", "volunteer", "other"):
        if _as_list(parsed_sections.get(key)):
            sections += 1

    if sections:
        return f"{sections} section{'s' if sections != 1 else ''}"
    return None
