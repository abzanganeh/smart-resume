"""Registry of optional free job-aggregator sources."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.config import settings
from app.services.career_watch.aggregators.arbeitnow import fetch_arbeitnow_jobs
from app.services.career_watch.aggregators.hn_whos_hiring import fetch_hn_whos_hiring_jobs
from app.services.career_watch.aggregators.remoteok import fetch_remoteok_jobs
from app.services.career_watch.aggregators.remotive import fetch_remotive_jobs
from app.services.career_watch.aggregators.usajobs import fetch_usajobs_jobs
from app.services.career_watch.aggregators.weworkremotely import fetch_weworkremotely_jobs
from app.services.career_watch.types import ParsedJob

FetchFn = Callable[..., Awaitable[list[ParsedJob]]]


@dataclass(frozen=True, slots=True)
class AggregatorSource:
    id: str
    enabled: bool
    fetch: FetchFn


def _usajobs_enabled() -> bool:
    return bool(
        settings.JOB_AGGREGATOR_USAJOBS_ENABLED
        and settings.USAJOBS_API_KEY.strip()
        and settings.USAJOBS_USER_AGENT.strip()
    )


def all_aggregator_sources() -> tuple[AggregatorSource, ...]:
    return (
        AggregatorSource(
            "remotive",
            settings.JOB_AGGREGATOR_REMOTIVE_ENABLED,
            fetch_remotive_jobs,
        ),
        AggregatorSource(
            "remoteok",
            settings.JOB_AGGREGATOR_REMOTEOK_ENABLED,
            fetch_remoteok_jobs,
        ),
        AggregatorSource(
            "arbeitnow",
            settings.JOB_AGGREGATOR_ARBEITNOW_ENABLED,
            fetch_arbeitnow_jobs,
        ),
        AggregatorSource(
            "weworkremotely",
            settings.JOB_AGGREGATOR_WEWORKREMOTELY_ENABLED,
            fetch_weworkremotely_jobs,
        ),
        AggregatorSource(
            "usajobs",
            _usajobs_enabled(),
            fetch_usajobs_jobs,
        ),
        AggregatorSource(
            "hn_whos_hiring",
            settings.JOB_AGGREGATOR_HN_WHOS_HIRING_ENABLED,
            fetch_hn_whos_hiring_jobs,
        ),
    )


def enabled_aggregator_sources() -> list[AggregatorSource]:
    return [source for source in all_aggregator_sources() if source.enabled]


__all__ = [
    "AggregatorSource",
    "all_aggregator_sources",
    "enabled_aggregator_sources",
]
