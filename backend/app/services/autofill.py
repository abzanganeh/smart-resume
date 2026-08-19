"""Autofill payload generation for the Flint browser extension."""

from __future__ import annotations

from urllib.parse import urlparse

from app.models.session import Session

GREENHOUSE_FIELD_SELECTORS: dict[str, str] = {
    "first_name": "[name='job_application[first_name]']",
    "last_name": "[name='job_application[last_name]']",
    "email": "[name='job_application[email]']",
    "phone": "[name='job_application[phone]']",
    "resume": "[name='job_application[resume]']",
    "linkedin_url": "[name='job_application[urls][LinkedIn]']",
    "work_authorization": "[name='job_application[answers][work_authorization]']",
}

RECENT_TAILORED_LIMIT = 20


def detect_platform(url: str | None) -> str:
    if not url:
        return "unknown"
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("greenhouse.io"):
        return "greenhouse"
    if host.endswith("linkedin.com"):
        return "linkedin"
    if host.endswith("lever.co"):
        return "lever"
    if host.endswith("ashbyhq.com"):
        return "ashby"
    return "unknown"


def split_name(name: str) -> tuple[str, str]:
    cleaned = name.strip()
    if not cleaned:
        return "", ""
    parts = cleaned.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def extract_contact(session: Session) -> dict[str, str]:
    if session.phase3_output and isinstance(session.phase3_output.contact, dict):
        return {str(k): str(v) for k, v in session.phase3_output.contact.items() if v}
    if session.resume_parsed and session.resume_parsed.contact:
        parsed = session.resume_parsed.contact.model_dump()
        return {str(k): str(v) for k, v in parsed.items() if v}
    if session.user_info:
        info = session.user_info.model_dump()
        return {str(k): str(v) for k, v in info.items() if v}
    return {}


def build_autofill_fields(contact: dict[str, str], platform: str) -> list[dict[str, str]]:
    # Only Greenhouse has known DOM selectors today; other platforms (linkedin,
    # unknown) still get concept-keyed fields so the extension can resolve
    # inputs via heuristics client-side.
    selectors = GREENHOUSE_FIELD_SELECTORS if platform == "greenhouse" else None

    first_name, last_name = split_name(str(contact.get("name") or ""))
    values: list[tuple[str, str]] = [
        ("first_name", first_name),
        ("last_name", last_name),
        ("email", str(contact.get("email") or "")),
        ("phone", str(contact.get("phone") or "")),
        ("linkedin_url", str(contact.get("linkedin") or "")),
    ]

    fields: list[dict[str, str]] = []
    for key, value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        fields.append(
            {
                "key": key,
                "selector": selectors[key] if selectors else "",
                "value": cleaned,
            }
        )

    # File inputs are surfaced for manual attachment — never claim they were filled.
    fields.append(
        {
            "key": "resume",
            "selector": selectors["resume"] if selectors else "",
            "value": "",
        }
    )
    return fields


def url_host(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower()
