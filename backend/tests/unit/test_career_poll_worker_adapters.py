"""Unit tests for Career Watch worker ATS adapters (slice 8)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ADAPTERS_PATH = (
    Path(__file__).resolve().parents[3] / "infra" / "career_poll_worker" / "adapters.py"
)


def _load_adapters():
    spec = importlib.util.spec_from_file_location("career_poll_adapters", _ADAPTERS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["career_poll_adapters"] = module
    spec.loader.exec_module(module)
    return module


def test_user_agent_is_taliocv() -> None:
    adapters = _load_adapters()
    assert "TalioCV" in adapters.USER_AGENT
    assert "taliocv.com" in adapters.USER_AGENT


def test_parse_greenhouse_jobs() -> None:
    adapters = _load_adapters()
    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Engineer",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            }
        ]
    }
    jobs = adapters.parse_greenhouse_jobs(payload, careers_url="https://acme.com/careers")
    assert len(jobs) == 1
    assert jobs[0]["external_job_id"] == "123"
    assert jobs[0]["title"] == "Engineer"


def test_parse_lever_jobs() -> None:
    adapters = _load_adapters()
    payload = [
        {
            "id": "abc",
            "text": "Designer",
            "hostedUrl": "https://jobs.lever.co/acme/abc",
            "categories": {"location": "New York"},
        }
    ]
    jobs = adapters.parse_lever_jobs(payload, careers_url="https://acme.com")
    assert jobs[0]["external_job_id"] == "abc"
    assert jobs[0]["location"] == "New York"


def test_parse_ashby_jobs() -> None:
    adapters = _load_adapters()
    payload = {
        "jobs": [
            {
                "id": "job-1",
                "title": "PM",
                "location": "Seattle",
                "jobUrl": "https://jobs.ashbyhq.com/acme/job-1",
            }
        ]
    }
    jobs = adapters.parse_ashby_jobs(payload, careers_url="https://acme.com")
    assert jobs[0]["external_job_id"] == "job-1"
    assert jobs[0]["apply_url"].endswith("job-1")
