"""Free job-aggregator adapters (feature-flagged, default off)."""

from app.services.career_watch.aggregators.registry import (
    AggregatorSource,
    all_aggregator_sources,
    enabled_aggregator_sources,
)
from app.services.career_watch.aggregators.sync import (
    stable_external_id,
    sync_aggregator_jobs_to_cache,
)

__all__ = [
    "AggregatorSource",
    "all_aggregator_sources",
    "enabled_aggregator_sources",
    "stable_external_id",
    "sync_aggregator_jobs_to_cache",
]
