"""Career Watch ORM models — table metadata and constraints (slice 11)."""

from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint

from app.db.base import Base
from app.models.career_watch import (
    CareerAlert,
    CareerAlertStatus,
    CareerAtsType,
    CareerJobCache,
    UserWatchedCompany,
    WatchedCompany,
)

pytestmark = pytest.mark.unit


def test_career_watch_tables_registered_in_metadata() -> None:
    names = Base.metadata.tables.keys()
    for table in (
        "watched_companies",
        "user_watched_companies",
        "career_job_cache",
        "career_alerts",
    ):
        assert table in names


def test_watched_company_slug_unique() -> None:
    constraints = WatchedCompany.__table__.constraints
    unique = [
        c
        for c in constraints
        if isinstance(c, UniqueConstraint) and "slug" in {col.name for col in c.columns}
    ]
    assert unique, "watched_companies.slug must be unique"


def test_user_watched_company_pair_unique() -> None:
    constraints = UserWatchedCompany.__table__.constraints
    pair_unique = [
        c
        for c in constraints
        if isinstance(c, UniqueConstraint)
        and {col.name for col in c.columns} == {"user_id", "watched_company_id"}
    ]
    assert pair_unique


def test_career_job_cache_external_id_unique_per_company() -> None:
    constraints = CareerJobCache.__table__.constraints
    pair_unique = [
        c
        for c in constraints
        if isinstance(c, UniqueConstraint)
        and {col.name for col in c.columns}
        == {"watched_company_id", "external_job_id"}
    ]
    assert pair_unique


def test_career_alert_one_per_user_job() -> None:
    constraints = CareerAlert.__table__.constraints
    pair_unique = [
        c
        for c in constraints
        if isinstance(c, UniqueConstraint)
        and {col.name for col in c.columns} == {"user_id", "career_job_cache_id"}
    ]
    assert pair_unique


def test_career_ats_type_values() -> None:
    assert CareerAtsType.greenhouse.value == "greenhouse"
    assert CareerAtsType.generic_html.value == "generic_html"


def test_career_alert_status_values() -> None:
    assert CareerAlertStatus.pending.value == "pending"
    assert CareerAlertStatus.sent.value == "sent"
