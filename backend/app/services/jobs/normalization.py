"""Job record normalization helpers (SYSTEM_DESIGN_PHASE_2 §18.10)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

log = logging.getLogger(__name__)

# Hardcoded daily FX rates to USD (approximate; refreshed manually).
_FX_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "CAD": 0.73,
    "EUR": 1.08,
    "GBP": 1.27,
    "AUD": 0.65,
}

_US_STATE_RE = re.compile(r"^[A-Z]{2}$")

_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_eid", "ref", "source")


def normalize_apply_url(url: str | None) -> str | None:
    """Normalize an apply URL for stable dedup (scheme/host lowercased, tracking stripped)."""
    if not url or not url.strip():
        return None
    text = url.strip()
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/").lower()

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not any(k.lower().startswith(p) for p in _TRACKING_QUERY_PREFIXES)
        and k.lower() not in {"ref", "source", "fbclid", "gclid"}
    ]
    query = urlencode(sorted(query_pairs))
    return urlunparse((scheme, netloc, path, "", query, ""))


def compute_dedup_key(
    company: str,
    title: str,
    city: str | None,
    posted_date: datetime | date,
) -> str:
    """Build a deterministic, case-insensitive dedup key for job_cache rows."""
    city_part = city or ""
    if isinstance(posted_date, datetime):
        day = posted_date.date().isoformat()
    else:
        day = posted_date.isoformat()
    return f"{company.lower()}{title.lower()}{city_part}{day}"


def compute_dedup_key_v2(
    *,
    apply_url: str | None = None,
    ats_type: str | None = None,
    external_job_id: str | None = None,
    company: str = "",
    title: str = "",
    city: str | None = None,
    posted_date: datetime | date | None = None,
) -> str:
    """Build dedup key preferring normalized apply URL, then ATS id, then legacy key."""
    normalized_url = normalize_apply_url(apply_url)
    if normalized_url:
        return f"url:{normalized_url}"
    if ats_type and external_job_id:
        return f"ats:{ats_type.lower()}:{external_job_id.strip()}"
    if posted_date is None:
        posted_date = datetime.now().date()
    return compute_dedup_key(company, title, city, posted_date)


def normalize_salary(amount: int | float | None, currency: str | None) -> int | None:
    """Convert a salary amount to USD using a hardcoded FX table."""
    if amount is None:
        return None
    if currency is None or not currency.strip():
        log.warning(
            "unknown currency for salary normalization",
            extra={"currency": currency, "amount": amount},
        )
        return None
    code = currency.strip().upper()
    rate = _FX_TO_USD.get(code)
    if rate is None:
        log.warning(
            "unknown currency for salary normalization",
            extra={"currency": code, "amount": amount},
        )
        return None
    return int(round(float(amount) * rate))


def normalize_location(location_str: str | None) -> tuple[str | None, str | None]:
    """Split a location string into (city, country).

    Uses geopy when installed; otherwise a simple comma-split heuristic:
    ``"City, Country"`` or ``"City, ST, Country"``.
    """
    if not location_str or not location_str.strip():
        return None, None

    text = location_str.strip()

    try:
        from geopy.geocoders import Nominatim  # type: ignore[import-untyped]

        geolocator = Nominatim(user_agent="smart-resume-job-search")
        location = geolocator.geocode(text, addressdetails=True, timeout=3)
        if location and location.raw.get("address"):
            addr = location.raw["address"]
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("county")
            )
            country = addr.get("country")
            return city, country
    except ImportError:
        pass
    except Exception:
        log.debug("geopy geocode failed for %r", text, exc_info=True)

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) == 1:
        return parts[0], None
    if len(parts) == 2:
        return parts[0], parts[1]
    # "City, ST, Country" — middle token may be a US state abbreviation.
    if len(parts) >= 3 and _US_STATE_RE.match(parts[1].upper()):
        return parts[0], parts[-1]
    return parts[0], parts[-1]
