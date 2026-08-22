"""Unit tests for M19 free job-aggregator adapters (slice 5)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import settings
from app.services.career_watch.aggregators.arbeitnow import parse_arbeitnow_payload
from app.services.career_watch.aggregators.hn_whos_hiring import (
    parse_hn_search_payload,
    parse_hn_thread_comments,
)
from app.services.career_watch.aggregators.registry import (
    all_aggregator_sources,
    enabled_aggregator_sources,
)
from app.services.career_watch.aggregators.remoteok import parse_remoteok_payload
from app.services.career_watch.aggregators.remotive import parse_remotive_payload
from app.services.career_watch.aggregators.usajobs import parse_usajobs_payload
from app.services.career_watch.aggregators.weworkremotely import parse_wwr_rss

pytestmark = pytest.mark.unit


def test_all_aggregators_default_disabled() -> None:
    assert enabled_aggregator_sources() == []


def test_registry_enables_only_flagged_sources() -> None:
    with (
        patch.object(settings, "JOB_AGGREGATOR_REMOTIVE_ENABLED", True),
        patch.object(settings, "JOB_AGGREGATOR_REMOTEOK_ENABLED", True),
        patch.object(settings, "JOB_AGGREGATOR_USAJOBS_ENABLED", True),
        patch.object(settings, "USAJOBS_API_KEY", ""),
    ):
        enabled = {source.id for source in enabled_aggregator_sources()}
    assert enabled == {"remotive", "remoteok"}


def test_registry_usajobs_requires_credentials() -> None:
    with (
        patch.object(settings, "JOB_AGGREGATOR_USAJOBS_ENABLED", True),
        patch.object(settings, "USAJOBS_API_KEY", "key"),
        patch.object(settings, "USAJOBS_USER_AGENT", "user@example.com"),
    ):
        enabled = {source.id for source in enabled_aggregator_sources()}
    assert "usajobs" in enabled


def test_remotive_parse_fixture() -> None:
    jobs = parse_remotive_payload(
        [
            {
                "id": 42,
                "title": "Backend Engineer",
                "company_name": "Acme",
                "url": "https://remotive.com/remote-jobs/acme",
                "candidate_required_location": "Worldwide",
                "description": "Build APIs",
                "publication_date": "2026-01-15",
            }
        ]
    )
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].raw_payload["company"] == "Acme"


def test_remoteok_parse_skips_legal_banner_row() -> None:
    jobs = parse_remoteok_payload(
        [
            {"legal": "Remote OK is not affiliated"},
            {
                "slug": "acme-backend",
                "company": "Acme",
                "position": "Backend Engineer",
                "url": "https://remoteok.com/l/acme-backend",
                "description": "Remote role",
                "epoch": 1_735_689_600,
            },
        ]
    )
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].raw_payload["remote"] is True


def test_arbeitnow_parse_fixture() -> None:
    jobs = parse_arbeitnow_payload(
        [
            {
                "slug": "acme-backend-berlin",
                "title": "Backend Engineer",
                "company_name": "Acme GmbH",
                "url": "https://www.arbeitnow.com/view/acme-backend-berlin",
                "location": "Berlin, Germany",
                "description": "Python",
                "remote": True,
                "created_at": "2026-02-01T10:00:00Z",
            }
        ]
    )
    assert len(jobs) == 1
    assert jobs[0].location == "Berlin, Germany"
    assert jobs[0].raw_payload["remote"] is True


def test_weworkremotely_parse_rss_fixture() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Acme Corp: Backend Engineer</title>
      <link>https://weworkremotely.com/remote-jobs/acme-backend</link>
      <description>Remote Python role</description>
      <pubDate>Mon, 02 Feb 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
    jobs = parse_wwr_rss(xml)
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].raw_payload["company"] == "Acme Corp"


def test_usajobs_parse_fixture() -> None:
    jobs = parse_usajobs_payload(
        {
            "SearchResult": {
                "SearchResultItems": [
                    {
                        "MatchedObjectDescriptor": {
                            "PositionID": "12345",
                            "PositionTitle": "IT Specialist",
                            "OrganizationName": "Department of Example",
                            "PositionURI": "https://www.usajobs.gov/job/12345",
                            "PublicationStartDate": "2026-01-10T00:00:00Z",
                            "PositionLocation": [
                                {
                                    "CityName": "Washington",
                                    "CountrySubDivisionCode": "DC",
                                    "CountryCode": "United States",
                                }
                            ],
                            "UserArea": {
                                "Details": {
                                    "MajorDuties": ["Maintain systems", "Support users"]
                                }
                            },
                        }
                    }
                ]
            }
        }
    )
    assert len(jobs) == 1
    assert jobs[0].title == "IT Specialist"
    assert "Washington" in jobs[0].location
    assert jobs[0].raw_payload["company"] == "Department of Example"


def test_hn_whos_hiring_parse_thread_comments() -> None:
    story_id = "999"
    jobs = parse_hn_thread_comments(
        {
            "children": [
                {
                    "text": "Acme Corp | Backend Engineer | Remote | https://acme.example/jobs\n",
                },
                {"text": "Not a job line"},
            ]
        },
        thread_id=story_id,
    )
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].raw_payload["company"] == "Acme Corp"


def test_hn_search_payload_extracts_story_id() -> None:
    assert (
        parse_hn_search_payload({"hits": [{"objectID": "42424242"}]})
        == "42424242"
    )


def test_all_aggregator_sources_registered() -> None:
    ids = {source.id for source in all_aggregator_sources()}
    assert ids == {
        "remotive",
        "remoteok",
        "arbeitnow",
        "weworkremotely",
        "usajobs",
        "hn_whos_hiring",
    }
