"""Resolve ATS issue anchors to exact resume bullets for chat patch hydration."""

from __future__ import annotations

from typing import Any

from app.models.chat import ResumePatch
from app.models.qa import BlockingIssue, IssueAnchor


def _names_match(a: str, b: str) -> bool:
    left = " ".join(a.strip().lower().split())
    right = " ".join(b.strip().lower().split())
    if not left or not right:
        return False
    return left == right or left in right or right in left


def resolve_bullet_at_anchor(
    resume: dict[str, Any],
    anchor: IssueAnchor,
) -> dict[str, str] | None:
    """Return canonical section fields for a bullet at anchor, or None if stale."""
    bullet_index = anchor.bullet_index
    if bullet_index is None:
        return None

    if anchor.section == "experience":
        entries = resume.get("experience") or []
        if anchor.entry_index >= len(entries):
            return None
        entry = entries[anchor.entry_index]
        bullets = entry.get("bullets") or []
        if bullet_index >= len(bullets):
            return None
        company = str(entry.get("company") or "").strip()
        if not company:
            return None
        return {
            "section": "experience",
            "company": company,
            "bullet_old": str(bullets[bullet_index]),
        }

    if anchor.section == "projects":
        entries = resume.get("projects") or []
        if anchor.entry_index >= len(entries):
            return None
        entry = entries[anchor.entry_index]
        bullets = entry.get("bullets") or []
        if bullet_index >= len(bullets):
            return None
        name = str(entry.get("name") or "").strip()
        if not name:
            return None
        return {
            "section": "projects",
            "project_name": name,
            "project_bullet_old": str(bullets[bullet_index]),
        }

    if anchor.section == "education":
        entries = resume.get("education") or []
        if anchor.entry_index >= len(entries):
            return None
        entry = entries[anchor.entry_index]
        bullets = entry.get("bullets") or []
        if bullet_index >= len(bullets):
            return None
        institution = str(entry.get("institution") or "").strip()
        if not institution:
            return None
        return {
            "section": "education",
            "institution": institution,
            "education_bullet_old": str(bullets[bullet_index]),
        }

    return None


def build_anchor_target_block(
    resume: dict[str, Any],
    issues: list[BlockingIssue],
) -> str:
    """Human + machine-readable targets for the chat agent."""
    lines = [
        "ANCHORED FIX TARGETS (rewrite ONLY bullet_new — bullet_old is filled server-side):",
    ]
    for i, issue in enumerate(issues, start=1):
        if not issue.anchor:
            continue
        resolved = resolve_bullet_at_anchor(resume, issue.anchor)
        if not resolved:
            lines.append(
                f"{i}. [{issue.category}] {issue.description} — anchor stale, skip patch"
            )
            continue
        if resolved["section"] == "experience":
            lines.append(
                f'{i}. section=experience company="{resolved["company"]}"\n'
                f'   EXACT current bullet: "{resolved["bullet_old"]}"\n'
                f"   Fix intent: {issue.suggestion}"
            )
        elif resolved["section"] == "projects":
            lines.append(
                f'{i}. section=projects project_name="{resolved["project_name"]}"\n'
                f'   EXACT current bullet: "{resolved["project_bullet_old"]}"\n'
                f"   Fix intent: {issue.suggestion}"
            )
        else:
            lines.append(
                f'{i}. section=education institution="{resolved["institution"]}"\n'
                f'   EXACT current bullet: "{resolved["education_bullet_old"]}"\n'
                f"   Fix intent: {issue.suggestion}"
            )
    return "\n".join(lines)


def hydrate_patch_from_anchor(
    resume: dict[str, Any],
    patch: ResumePatch,
    anchor: IssueAnchor | None,
) -> ResumePatch:
    """Stamp bullet_old / company / project_name from live resume at anchor."""
    if anchor is None:
        return patch
    resolved = resolve_bullet_at_anchor(resume, anchor)
    if not resolved:
        patch.anchor = anchor
        return patch

    patch.anchor = anchor
    if resolved["section"] == "experience":
        patch.section = "experience"
        patch.company = resolved["company"]
        patch.bullet_old = resolved["bullet_old"]
    elif resolved["section"] == "projects":
        patch.section = "projects"
        patch.project_name = resolved["project_name"]
        patch.project_bullet_old = resolved["project_bullet_old"]
    elif resolved["section"] == "education":
        patch.section = "education"
        patch.institution = resolved["institution"]
        patch.education_bullet_old = resolved["education_bullet_old"]
    return patch


def match_anchor_for_patch(
    resume: dict[str, Any],
    patch: ResumePatch,
    target_issues: list[BlockingIssue],
) -> IssueAnchor | None:
    """Match a patch to the anchored issue it targets (not positional)."""
    matches: list[IssueAnchor] = []
    for issue in target_issues:
        if issue.anchor is None:
            continue
        resolved = resolve_bullet_at_anchor(resume, issue.anchor)
        if not resolved:
            continue
        if resolved["section"] == "experience" and patch.section == "experience":
            company = (patch.company or "").strip()
            if company and _names_match(company, resolved["company"]):
                matches.append(issue.anchor)
                continue
            if patch.bullet_new and not company:
                matches.append(issue.anchor)
        elif resolved["section"] == "projects" and patch.section == "projects":
            project_name = (patch.project_name or "").strip()
            if project_name and _names_match(project_name, resolved["project_name"]):
                matches.append(issue.anchor)
                continue
            if patch.project_bullet_new and not project_name:
                matches.append(issue.anchor)
    if len(matches) == 1:
        return matches[0]
    return None


def hydrate_chat_patches(
    resume: dict[str, Any],
    patches: list[ResumePatch],
    target_issues: list[BlockingIssue],
) -> list[ResumePatch]:
    """Attach anchors and canonical bullet_old to LLM patches."""
    if not any(issue.anchor is not None for issue in target_issues):
        return patches

    hydrated: list[ResumePatch] = []
    for patch in patches:
        anchor = patch.anchor or match_anchor_for_patch(resume, patch, target_issues)
        hydrated.append(hydrate_patch_from_anchor(resume, patch, anchor))

    return hydrated
