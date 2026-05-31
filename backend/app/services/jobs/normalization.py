"""Job record normalization helpers (SYSTEM_DESIGN_PHASE_2 §18.10)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

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


def normalize_salary(amount: int | float | None, currency: str | None) -> int | None:
    """Convert a salary amount to USD using a hardcoded FX table."""
    if amount is None:
        return None
    if currency is None:
        return int(round(float(amount)))
    code = currency.strip().upper()
    rate = _FX_TO_USD.get(code)
    if rate is None:
        log.warning("unknown currency for salary normalization: %s", code)
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
