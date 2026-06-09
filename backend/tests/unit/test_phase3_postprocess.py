"""Unit tests for Phase 3 post-processing."""

from __future__ import annotations

from app.agent.phase3_postprocess import (
    enforce_experience_bullet_limits,
    enforce_project_bullet_limits,
    is_category_skill_line,
    normalize_skills_to_categories,
    postprocess_tailored_output,
    skills_are_categorized,
)
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput


def test_is_category_skill_line() -> None:
    assert is_category_skill_line("AI & ML: Python, LLMs, RAG")
    assert not is_category_skill_line("Python")
    assert not is_category_skill_line("Write production-quality code for teams")


def test_normalize_flat_skills_to_categories() -> None:
    flat = [
        "Python",
        "Generative AI",
        "LLMs",
        "RAG",
        "FastAPI",
        "Kubernetes",
        "Docker",
        "MLOps",
        "Backend Engineering",
    ]
    result = normalize_skills_to_categories(flat, must_have_keywords=["Generative AI", "LLMs"])
    assert skills_are_categorized(result)
    assert all(":" in line for line in result)
    assert any("AI" in line for line in result)
    assert any("Python" in line or "FastAPI" in line for line in result)


def test_normalize_preserves_existing_categories() -> None:
    categorized = [
        "AI & Machine Learning: LLMs, RAG",
        "DevOps: Kubernetes, Docker",
    ]
    assert normalize_skills_to_categories(categorized) == categorized


def test_enforce_experience_bullet_limits() -> None:
    experience = [
        TailoredExperienceEntry(company="Current", bullets=[f"b{i}" for i in range(7)]),
        TailoredExperienceEntry(company="Prior", bullets=[f"p{i}" for i in range(5)]),
    ]
    trimmed = enforce_experience_bullet_limits(experience)
    assert len(trimmed[0].bullets) == 5
    assert len(trimmed[1].bullets) == 3
    assert len(trimmed[0].removed_bullets) == 2


def test_enforce_project_bullet_limits() -> None:
    projects = [{"name": "P1", "bullets": ["a", "b", "c", "d"]}]
    trimmed = enforce_project_bullet_limits(projects)
    assert len(trimmed[0]["bullets"]) == 3


def test_postprocess_tailored_output_integration() -> None:
    output = TailoredResumeOutput(
        skills=["Python", "LLMs", "Kubernetes"],
        experience=[
            TailoredExperienceEntry(company="Acme", bullets=["b1", "b2", "b3", "b4", "b5", "b6"]),
        ],
        projects=[{"name": "Proj", "bullets": ["x", "y", "z", "w"]}],
    )
    processed = postprocess_tailored_output(output, must_have_keywords=["LLMs"])
    assert skills_are_categorized(processed.skills)
    assert len(processed.experience[0].bullets) == 5
    assert len(processed.projects[0]["bullets"]) == 3
