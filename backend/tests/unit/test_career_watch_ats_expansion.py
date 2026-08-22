"""Unit tests for M19 ATS adapter expansion."""

from __future__ import annotations

import pytest

from app.models.career_watch import CareerAtsType
from app.services.career_watch.bamboohr import parse_bamboohr_payload
from app.services.career_watch.breezy import parse_breezy_payload
from app.services.career_watch.detect import detect_ats_from_url
from app.services.career_watch.personio import parse_personio_xml
from app.services.career_watch.recruitee import parse_recruitee_payload
from app.services.career_watch.registry import get_adapter
from app.services.career_watch.smartrecruiters import parse_smartrecruiters_payload
from app.services.career_watch.workable import parse_workable_payload


@pytest.mark.parametrize(
    ("url", "ats_type", "token"),
    [
        (
            "https://careers.smartrecruiters.com/AcmeCorp",
            CareerAtsType.smartrecruiters,
            "AcmeCorp",
        ),
        (
            "https://apply.workable.com/acme-corp",
            CareerAtsType.workable,
            "acme-corp",
        ),
        (
            "https://acme.recruitee.com/o/backend-engineer",
            CareerAtsType.recruitee,
            "acme",
        ),
        (
            "https://acme.breezy.hr/p/backend-engineer",
            CareerAtsType.breezy,
            "acme",
        ),
        (
            "https://acme.jobs.personio.com/job/123",
            CareerAtsType.personio,
            "acme",
        ),
        (
            "https://acme.bamboohr.com/careers",
            CareerAtsType.bamboohr,
            "acme",
        ),
    ],
)
def test_detect_new_ats_urls(url: str, ats_type: CareerAtsType, token: str) -> None:
    result = detect_ats_from_url(url)
    assert result.ats_type == ats_type
    assert result.board_token == token


def test_smartrecruiters_parse_jobs_and_empty_not_found() -> None:
    jobs = parse_smartrecruiters_payload(
        [
            {
                "id": "Posting1",
                "name": "Platform Engineer",
                "location": {"city": "Berlin", "country": "DE"},
                "ref": "https://careers.smartrecruiters.com/acme/Posting1",
                "releasedDate": "2026-01-15T10:00:00.000Z",
            }
        ],
        descriptions={"Posting1": "Build platforms"},
    )
    assert len(jobs) == 1
    assert jobs[0].title == "Platform Engineer"
    assert jobs[0].description_text == "Build platforms"
    assert parse_smartrecruiters_payload([]) == []


def test_workable_parse_jobs_and_empty_not_found() -> None:
    jobs = parse_workable_payload(
        [
            {
                "shortcode": "ABC123",
                "title": "Data Analyst",
                "location": {"location_str": "Remote"},
                "description": "Analyze data",
                "url": "https://apply.workable.com/acme/j/ABC123",
                "published": "2026-02-01T08:00:00Z",
            }
        ]
    )
    assert jobs[0].external_job_id == "ABC123"
    assert parse_workable_payload([]) == []


def test_recruitee_parse_jobs_and_empty_not_found() -> None:
    jobs = parse_recruitee_payload(
        [
            {
                "id": 42,
                "title": "Support Engineer",
                "location": "London",
                "description": "Help customers",
                "careers_url": "https://acme.recruitee.com/o/support-engineer",
                "published_at": "2026-02-10T12:00:00Z",
            }
        ]
    )
    assert jobs[0].external_job_id == "42"
    assert parse_recruitee_payload([]) == []


def test_breezy_parse_jobs_and_empty_not_found() -> None:
    jobs = parse_breezy_payload(
        [
            {
                "_id": "pos-1",
                "friendly_id": "backend-engineer",
                "name": "Backend Engineer",
                "location": {"name": "Austin"},
            }
        ],
        descriptions={"pos-1": "Ship APIs"},
    )
    assert jobs[0].description_text == "Ship APIs"
    assert parse_breezy_payload([]) == []


def test_personio_parse_xml_jobs() -> None:
    xml = """
    <workday-job-feed>
      <position>
        <id>777</id>
        <name>HR Generalist</name>
        <office>Munich</office>
        <description>People ops</description>
        <url>https://acme.jobs.personio.com/job/777</url>
        <createdAt>2026-03-01T09:00:00Z</createdAt>
      </position>
    </workday-job-feed>
    """
    jobs = parse_personio_xml(xml)
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "777"
    assert jobs[0].location == "Munich"


def test_personio_parse_empty_xml() -> None:
    assert parse_personio_xml("<workday-job-feed></workday-job-feed>") == []


def test_bamboohr_parse_jobs_and_empty_not_found() -> None:
    jobs = parse_bamboohr_payload(
        [
            {
                "id": "99",
                "jobOpeningName": "Account Executive",
                "location": {"city": "Denver", "state": "CO"},
                "jobOpeningShareUrl": "https://acme.bamboohr.com/careers/99",
            }
        ],
        descriptions={"99": "Sell software"},
    )
    assert jobs[0].title == "Account Executive"
    assert parse_bamboohr_payload([]) == []


@pytest.mark.parametrize(
    ("ats_type", "class_name"),
    [
        (CareerAtsType.smartrecruiters, "SmartRecruitersAdapter"),
        (CareerAtsType.workable, "WorkableAdapter"),
        (CareerAtsType.recruitee, "RecruiteeAdapter"),
        (CareerAtsType.breezy, "BreezyAdapter"),
        (CareerAtsType.personio, "PersonioAdapter"),
        (CareerAtsType.bamboohr, "BambooHrAdapter"),
    ],
)
def test_registry_returns_new_adapters(ats_type: CareerAtsType, class_name: str) -> None:
    adapter = get_adapter(ats_type)
    assert adapter.__class__.__name__ == class_name
