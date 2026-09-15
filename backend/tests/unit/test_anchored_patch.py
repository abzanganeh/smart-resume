"""Unit tests for anchor-based chat patch hydration."""

from app.models.qa import BlockingIssue, IssueAnchor
from app.services.anchored_patch import (
    build_anchor_target_block,
    enrich_issues_with_inferred_anchors,
    hydrate_chat_patches,
    infer_anchor_from_issue,
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


def test_infer_anchor_from_bullet_too_short_suggestion() -> None:
    issue = BlockingIssue(
        category="bullet",
        description="Bullet length sweet spot (12-25 words)",
        suggestion=(
            "Bullet too short (10 words): Spearheaded quality ownership across multiple stacks."
        ),
        impact="medium",
        fix_effort="manual_rewrite",
    )
    anchor = infer_anchor_from_issue(RESUME, issue)
    assert anchor is not None
    assert anchor.section == "experience"
    assert anchor.entry_index == 0
    assert anchor.bullet_index == 0


def test_enrich_issues_adds_inferred_anchor() -> None:
    issue = BlockingIssue(
        category="bullet",
        description="Bullet length sweet spot (12-25 words)",
        suggestion=(
            "Bullet too short (10 words): Spearheaded quality ownership across multiple stacks."
        ),
        impact="medium",
        fix_effort="manual_rewrite",
    )
    enriched = enrich_issues_with_inferred_anchors(RESUME, [issue])
    assert enriched[0].anchor is not None
    assert infer_anchor_from_issue(RESUME, enriched[0]) is not None


def test_hydrate_chat_patches_positional_binds_wrong_llm_company() -> None:
    from app.models.chat import ResumePatch

    issue = BlockingIssue(
        category="metric",
        description="Add a metric to AWS migration bullet",
        suggestion="Add a quantified outcome such as reduced migration time by 35%.",
        impact="medium",
        fix_effort="user_input",
        anchor=IssueAnchor(section="experience", entry_index=0, bullet_index=0),
    )
    patch = ResumePatch(
        section="experience",
        description="Add quantifiable metric to AWS migration bullet",
        company="Northwind Payments",
        bullet_old="Wrong bullet copied from fix intent.",
        bullet_new=(
            "Spearheaded quality ownership across multiple stacks, "
            "reducing production defects by 35%."
        ),
    )
    hydrated = hydrate_chat_patches(RESUME, [patch], [issue])[0]
    assert hydrated.company == "IdMe24"
    assert "Spearheaded quality ownership" in (hydrated.bullet_old or "")
    assert hydrated.anchor == issue.anchor


def test_hydrate_chat_patches_swapped_companies_do_not_misbind() -> None:
    from app.models.chat import ResumePatch

    resume = {
        "experience": [
            {
                "company": "Acme Corp",
                "title": "Engineer",
                "bullets": ["Built APIs for payments."],
            },
            {
                "company": "Northwind Payments",
                "title": "Engineer",
                "bullets": ["Led AWS migration for payment processing platform."],
            },
        ],
        "projects": [],
    }
    issues = [
        BlockingIssue(
            category="metric",
            description="Acme metric",
            suggestion="Add metric to Acme bullet.",
            impact="medium",
            fix_effort="user_input",
            anchor=IssueAnchor(section="experience", entry_index=0, bullet_index=0),
        ),
        BlockingIssue(
            category="metric",
            description="Northwind metric",
            suggestion="Add metric to AWS migration bullet.",
            impact="medium",
            fix_effort="user_input",
            anchor=IssueAnchor(section="experience", entry_index=1, bullet_index=0),
        ),
    ]
    patches = [
        ResumePatch(
            section="experience",
            description="Northwind fix",
            company="Northwind Payments",
            bullet_old="Led AWS migration for payment processing platform.",
            bullet_new="Led AWS migration for payment processing platform, reducing cutover time by 35%.",
        ),
        ResumePatch(
            section="experience",
            description="Acme fix",
            company="Acme Corp",
            bullet_old="Built APIs for payments.",
            bullet_new="Built APIs for payments, processing 2M transactions daily.",
        ),
    ]
    hydrated = hydrate_chat_patches(resume, patches, issues)
    assert hydrated[0].company == "Northwind Payments"
    assert "AWS migration" in (hydrated[0].bullet_old or "")
    assert hydrated[0].anchor == issues[1].anchor
    assert hydrated[1].company == "Acme Corp"
    assert hydrated[1].anchor == issues[0].anchor


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
