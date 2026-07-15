"""Unit tests for standalone checkup helpers."""

from __future__ import annotations

from app.models.resume import EducationEntry, ExperienceEntry, ParsedResume, ProjectEntry
from app.services.checkup_service import parsed_to_tailored


def test_parsed_to_tailored_maps_sections() -> None:
    parsed = ParsedResume(
        summary="Data engineer.",
        skills=["Languages: Python, SQL"],
        experience=[
            ExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020-2024",
                bullets=["Built pipelines"],
            )
        ],
        projects=[ProjectEntry(name="ETL Tool", description="Batch jobs", bullets=[])],
        education=[EducationEntry(degree="B.S.", institution="State U", year="2020")],
    )
    tailored = parsed_to_tailored(parsed)
    assert tailored.summary == "Data engineer."
    assert tailored.experience[0].company == "Acme"
    assert tailored.projects[0]["name"] == "ETL Tool"
    assert tailored.education[0].institution == "State U"
