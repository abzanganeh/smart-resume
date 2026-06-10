"""Chat agent description fallback tests.

The Phase 4 LLM frequently emits valid patches without the optional
``description`` field. Before the fallback was added, this caused
``complete_structured`` to raise after 3 retries and the user saw "I had
trouble processing that request" no matter what they typed. These tests
lock in the synthesized labels so any regression breaks the build.
"""
from __future__ import annotations

from app.agent.chat import _fill_missing_descriptions, _synthesize_description
from app.models.chat import ChatResponse, NewProject, ResumePatch


def test_resume_patch_description_is_optional() -> None:
    # Without a default, this would have raised a pydantic ValidationError
    # the moment the LLM omitted the field.
    patch = ResumePatch(section="summary", new_summary="Hello.")
    assert patch.description == ""


def test_summary_rewrite_synthesizes_label() -> None:
    patch = ResumePatch(section="summary", new_summary="New summary text.")
    assert _synthesize_description(patch) == "Rewrite summary"


def test_skills_add_and_remove_labels() -> None:
    add_only = ResumePatch(section="skills", add_skills=["Python", "SQL"])
    assert _synthesize_description(add_only) == "Add skills: Python, SQL"

    remove_only = ResumePatch(section="skills", remove_skills=["COBOL"])
    assert _synthesize_description(remove_only) == "Remove skills: COBOL"

    both = ResumePatch(section="skills", add_skills=["Go"], remove_skills=["Perl"])
    assert _synthesize_description(both) == "Add Go; remove Perl"


def test_experience_bullet_rewrite_label() -> None:
    patch = ResumePatch(
        section="experience",
        company="Acme",
        bullet_old="Did stuff.",
        bullet_new="Shipped Python service handling 1M req/day.",
    )
    assert _synthesize_description(patch) == "Rewrite a bullet at Acme"


def test_experience_delete_label() -> None:
    patch = ResumePatch(section="experience", company="Acme", delete_experience=True)
    assert _synthesize_description(patch) == "Remove Acme entry"


def test_new_project_label() -> None:
    patch = ResumePatch(
        section="projects",
        new_project=NewProject(name="Fraud Shield AI", bullets=["x"]),
    )
    assert _synthesize_description(patch) == "Add project: Fraud Shield AI"


def test_fill_missing_descriptions_only_overwrites_empty_strings() -> None:
    response = ChatResponse(
        reply="ok",
        patches=[
            ResumePatch(section="summary", new_summary="A.", description="Custom label"),
            ResumePatch(section="skills", add_skills=["Python"]),
        ],
    )
    filled = _fill_missing_descriptions(response)

    assert filled.patches[0].description == "Custom label"
    assert filled.patches[1].description == "Add skills: Python"
