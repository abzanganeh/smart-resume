"""Auto-detect ATS type and board token from a careers page URL."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models.career_watch import CareerAtsType
from app.services.career_watch.types import AtsDetectionResult

_GREENHOUSE_RE = re.compile(
    r"(?:boards\.greenhouse\.io|job-boards\.greenhouse\.io)/([^/?#]+)",
    re.IGNORECASE,
)
_LEVER_RE = re.compile(r"jobs\.lever\.co/([^/?#]+)", re.IGNORECASE)
_ASHBY_RE = re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.IGNORECASE)
_WORKDAY_HOST = "myworkdayjobs.com"


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{url.strip()}")
    return parsed.geturl()


def detect_ats_from_url(url: str) -> AtsDetectionResult:
    """Return ATS metadata inferred from ``url``."""
    normalized = _normalize_url(url)
    path = urlparse(normalized)

    if match := _GREENHOUSE_RE.search(normalized):
        token = match.group(1)
        return AtsDetectionResult(
            ats_type=CareerAtsType.greenhouse,
            board_token=token,
            careers_page_url=normalized,
            company_name=token.replace("-", " ").title(),
        )

    if match := _LEVER_RE.search(normalized):
        token = match.group(1)
        return AtsDetectionResult(
            ats_type=CareerAtsType.lever,
            board_token=token,
            careers_page_url=normalized,
            company_name=token.replace("-", " ").title(),
        )

    if match := _ASHBY_RE.search(normalized):
        token = match.group(1)
        return AtsDetectionResult(
            ats_type=CareerAtsType.ashby,
            board_token=token,
            careers_page_url=normalized,
            company_name=token.replace("-", " ").title(),
        )

    if "myworkdayjobs.com" in path.netloc.lower():
        tenant = path.netloc.split(".")[0]
        segments = [segment for segment in path.path.split("/") if segment]
        site = segments[0] if segments else "External"
        return AtsDetectionResult(
            ats_type=CareerAtsType.workday,
            board_token=f"{tenant}/{site}",
            careers_page_url=normalized,
            company_name=tenant.replace("-", " ").title(),
        )

    company_hint = path.netloc.split(".")[0].replace("-", " ").title()
    return AtsDetectionResult(
        ats_type=CareerAtsType.generic_html,
        board_token=None,
        careers_page_url=normalized,
        company_name=company_hint or None,
    )


__all__ = ["detect_ats_from_url"]
