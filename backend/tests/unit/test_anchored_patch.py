"""Unit tests for anchor-based chat patch hydration."""

from app.models.qa import BlockingIssue, IssueAnchor
from app.services.anchored_patch import (
    build_anchor_target_block,
    hydrate_chat_patches,
    resolve_bullet_at_anchor,
)


RESUME = {
    "experience": [
        {
            "company": "IdMe24",
            "title": "Software Engineer",
            "bullets": ["Spearheaded quality ownership across multiple stacks."],
        }
    ],
    "projects": [
        {
            "name": "Flint — Meeting Co-Pilot",
            "bullets": ["Local-first AI desktop co-pilot with Whisper transcription."],
        }
    ],
}


def test_resolve_bullet_at_anchor_for_project() -> None:
    anchor = IssueAnchor(section="projects", entry_index=0, bullet_index=0)
    resolved = resolve_bullet_at_anchor(RESUME, anchor)
    assert resolved is not None
    assert resolved["project_name"] == "Flint — Meeting Co-Pilot"
    assert "Local-first AI desktop co-pilot" in resolved["project_bullet_old"]


def test_hydrate_chat_patches_overwrites_llm_bullet_old() -> None:
    from app.models.chat import ResumePatch

    issue = BlockingIssue(
        category="bullet",
        description="Strong action verbs",
        suggestion="Open with a stronger verb: Championed quality ownership…",
        impact="medium",
        fix_effort="manual_rewrite",
        anchor=IssueAnchor(section="projects", entry_index=0, bullet_index=0),
    )
    patch = ResumePatch(
        section="projects",
        description="Rewrite bullet",
        project_name="Flint",
        project_bullet_old="Open with a stronger verb: Championed…",
        project_bullet_new="Engineered local-first AI desktop co-pilot with Whisper transcription.",
    )
    hydrated = hydrate_chat_patches(RESUME, [patch], [issue])[0]
    assert hydrated.project_name == "Flint — Meeting Co-Pilot"
    assert "Local-first AI desktop co-pilot" in (hydrated.project_bullet_old or "")
    assert hydrated.anchor == issue.anchor


def test_match_anchor_for_patch_by_project_name() -> None:
    from app.models.chat import ResumePatch

    issue = BlockingIssue(
        category="bullet",
        description="Strong action verbs",
        suggestion="Open with a stronger verb",
        impact="medium",
        fix_effort="manual_rewrite",
        anchor=IssueAnchor(section="projects", entry_index=0, bullet_index=0),
    )
    patch = ResumePatch(
        section="projects",
        description="Rewrite bullet",
        project_name="Flint",
        project_bullet_new="Engineered local-first AI desktop co-pilot.",
    )
    from app.services.anchored_patch import match_anchor_for_patch

    anchor = match_anchor_for_patch(RESUME, patch, [issue])
    assert anchor == issue.anchor


def test_match_anchor_for_patch_refuses_ambiguous_project_name() -> None:
    from app.models.chat import ResumePatch

    resume = {
        **RESUME,
        "projects": [
            {"name": "FlintApply", "bullets": ["Resume tailoring."]},
            {"name": "FlintGuide", "bullets": ["Interview co-pilot."]},
        ],
    }
    issues = [
        BlockingIssue(
            category="bullet",
            description="First Flint project",
            suggestion="Improve bullet",
            impact="medium",
            fix_effort="manual_rewrite",
            anchor=IssueAnchor(section="projects", entry_index=0, bullet_index=0),
        ),
        BlockingIssue(
            category="bullet",
            description="Second Flint project",
            suggestion="Improve bullet",
            impact="medium",
            fix_effort="manual_rewrite",
            anchor=IssueAnchor(section="projects", entry_index=1, bullet_index=0),
        ),
    ]
    patch = ResumePatch(
        section="projects",
        description="Rewrite bullet",
        project_name="Flint",
        project_bullet_new="Should not bind.",
    )
    from app.services.anchored_patch import match_anchor_for_patch

    assert match_anchor_for_patch(resume, patch, issues) is None


def test_hydrate_chat_patches_ignores_unknown_llm_anchor() -> None:
    from app.models.chat import ResumePatch

    patch = ResumePatch(
        section="projects",
        description="Rewrite bullet",
        project_bullet_new="Injected rewrite.",
        anchor=IssueAnchor(section="projects", entry_index=0, bullet_index=0),
    )
    hydrated = hydrate_chat_patches(RESUME, [patch], [])[0]
    assert hydrated.project_bullet_old is None


def test_resolve_bullet_at_anchor_returns_none_for_oob_index() -> None:
    assert resolve_bullet_at_anchor(
        RESUME,
        IssueAnchor(section="projects", entry_index=9, bullet_index=0),
    ) is None
    assert resolve_bullet_at_anchor(
        RESUME,
        IssueAnchor(section="projects", entry_index=0, bullet_index=9),
    ) is None


def test_build_anchor_target_block_includes_exact_bullet() -> None:
    issue = BlockingIssue(
        category="bullet",
        description="Strong action verbs",
        suggestion="Open with a stronger verb",
        impact="medium",
        fix_effort="manual_rewrite",
        anchor=IssueAnchor(section="experience", entry_index=0, bullet_index=0),
    )
    block = build_anchor_target_block(RESUME, [issue])
    assert "EXACT current bullet" in block
    assert "Spearheaded quality ownership" in block
