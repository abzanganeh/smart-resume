"""Unit tests for master-resume-hash tracking on preferred titles."""

from __future__ import annotations

import uuid

from app.models.user import User
from app.services.jobs.preferred_titles import (
    MIN_PREFERRED_JOB_TITLES,
    PREFERRED_TITLES_SOURCE_HASH_KEY,
    compute_master_resume_hash,
    get_preferred_titles_source_hash,
    has_confirmed_preferred_titles,
    is_source_stale,
    set_preferred_titles,
)


def _make_user() -> User:
    """Detached User stub — job_default_filters is the only mutable path we exercise."""
    user = User(
        id=uuid.uuid4(),
        email="hash@example.com",
        password_hash="",
        display_name="Hash Test",
    )
    user.job_default_filters = {}
    return user


def test_min_titles_is_five() -> None:
    assert MIN_PREFERRED_JOB_TITLES == 5


def test_hash_stable_across_whitespace_edits() -> None:
    a = compute_master_resume_hash("Senior QA Engineer at TrustCo. Python automation.")
    b = compute_master_resume_hash(
        "  Senior QA Engineer at   TrustCo.\nPython automation.  \n"
    )
    assert a == b


def test_hash_changes_on_substantive_edit() -> None:
    a = compute_master_resume_hash("Software Engineer at Acme.")
    b = compute_master_resume_hash(
        "Software Engineer at Acme. Now leading a five-person mobile team."
    )
    assert a != b


def test_hash_empty_input_is_deterministic() -> None:
    assert compute_master_resume_hash(None) == compute_master_resume_hash("")


def test_set_preferred_titles_persists_source_hash_when_confirmed() -> None:
    user = _make_user()
    titles = [
        "Backend Engineer",
        "Software Engineer",
        "Platform Engineer",
        "API Engineer",
        "Python Engineer",
    ]
    saved = set_preferred_titles(user, titles, source_hash="sha256:abc")
    assert saved == titles
    assert has_confirmed_preferred_titles(user)
    assert get_preferred_titles_source_hash(user) == "sha256:abc"


def test_hash_cleared_when_titles_drop_below_min() -> None:
    user = _make_user()
    user.job_default_filters = {PREFERRED_TITLES_SOURCE_HASH_KEY: "old"}
    saved = set_preferred_titles(user, ["Only One Title"], source_hash="new")
    assert saved == ["Only One Title"]
    assert not has_confirmed_preferred_titles(user)
    assert get_preferred_titles_source_hash(user) is None


def test_is_source_stale_false_when_hash_matches() -> None:
    user = _make_user()
    titles = ["A Engineer", "B Engineer", "C Engineer", "D Engineer", "E Engineer"]
    set_preferred_titles(user, titles, source_hash="hash-v1")
    assert not is_source_stale(user, current_hash="hash-v1")


def test_is_source_stale_true_when_hash_diverges() -> None:
    user = _make_user()
    titles = ["A Engineer", "B Engineer", "C Engineer", "D Engineer", "E Engineer"]
    set_preferred_titles(user, titles, source_hash="hash-v1")
    assert is_source_stale(user, current_hash="hash-v2")


def test_is_source_stale_true_when_stored_hash_missing_but_confirmed() -> None:
    """Users confirmed before hashes existed should be nudged to regenerate once."""
    user = _make_user()
    user.job_default_filters = {
        "preferred_titles": [
            "A Engineer",
            "B Engineer",
            "C Engineer",
            "D Engineer",
            "E Engineer",
        ],
        "preferred_titles_confirmed_at": "2026-01-01T00:00:00Z",
    }
    assert is_source_stale(user, current_hash="any-current-hash")


def test_is_source_stale_false_when_unconfirmed() -> None:
    user = _make_user()
    assert not is_source_stale(user, current_hash="anything")
