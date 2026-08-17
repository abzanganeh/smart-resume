"""Retrieval config — critical section floor includes projects."""

from app.services.retrieval.config import CRITICAL_SECTIONS, is_critical_section


def test_project_section_is_critical() -> None:
    assert "project" in CRITICAL_SECTIONS
    assert is_critical_section("project") is True


def test_skills_remain_non_critical() -> None:
    assert is_critical_section("skills") is False
