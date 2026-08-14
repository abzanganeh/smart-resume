"""Career Watch matcher unit tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.career_watch import CareerJobCache
from app.services.career_watch.matcher import keyword_match_score


def _job(**kwargs: object) -> CareerJobCache:
    defaults = {
        "id": uuid.uuid4(),
        "watched_company_id": uuid.uuid4(),
        "external_job_id": "1",
        "title": "Senior Backend Engineer",
        "location": "Remote",
        "description_text": "Python, FastAPI, PostgreSQL",
        "description_hash": "abc",
        "first_seen_at": datetime.now(timezone.utc),
        "last_seen_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return CareerJobCache(**defaults)  # type: ignore[arg-type]


def test_keyword_match_score_hits() -> None:
    job = _job()
    score, reason = keyword_match_score(["python", "backend"], job)
    assert score > 0
    assert "python" in reason.lower()


def test_keyword_match_score_miss() -> None:
    job = _job(title="Office Manager")
    score, reason = keyword_match_score(["kernel", "rust"], job)
    assert score == 0.0
    assert reason == ""


def test_keyword_match_default_without_keywords() -> None:
    job = _job()
    score, reason = keyword_match_score([], job)
    assert score == 0.5
    assert "default" in reason
