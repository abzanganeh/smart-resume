"""Job search services (cache, normalization, alerts)."""

from app.services.jobs.cache_writer import upsert_job_cache
from app.services.jobs.normalization import (
    compute_dedup_key,
    compute_dedup_key_v2,
    normalize_apply_url,
    normalize_location,
    normalize_salary,
)

__all__ = [
    "compute_dedup_key",
    "compute_dedup_key_v2",
    "normalize_apply_url",
    "normalize_location",
    "normalize_salary",
    "upsert_job_cache",
]
