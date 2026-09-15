"""Resolve ATS issue anchors to exact resume bullets for chat patch hydration."""

from __future__ import annotations

from typing import Any

from app.models.chat import ResumePatch
from app.models.qa import BlockingIssue, IssueAnchor


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _names_match(a: str, b: str) -> bool:
    left = _normalize_name(a)
    right = _normalize_name(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _normalize_bullet(value: str) -> str:
    return " ".join(value.strip().split())


# Prefix match only when the hint is long enough to avoid cross-bullet collisions.
_ANCHOR_HINT_PREFIX_LEN = 16


def _bullet_hint_matches(candidate: str, hint: str) -> bool:
    bullet = _normalize_bullet(candidate)
    needle = _normalize_bullet(hint.rstrip("…"))
    if not bullet or not needle:
        return False
    if bullet == needle:
        return True
    if bullet.startswith(needle) or needle.startswith(bullet):
        return True
    if (
        len(needle) >= _ANCHOR_HINT_PREFIX_LEN
        and needle[:_ANCHOR_HINT_PREFIX_LEN] in bullet
    ):
        return True
    return False


def _bullet_hint_from_issue(issue: BlockingIssue) -> str | None:
    text = issue.suggestion.strip()
    if not text:
        return None
    hint = text.rsplit(":", 1)[-1].strip().rstrip("…").strip()
    return hint if len(hint) >= 8 else None


def infer_anchor_from_issue(
    resume: dict[str, Any],
    issue: BlockingIssue,
) -> IssueAnchor | None:
    """Best-effort anchor when Phase 4 stored suggestion text but no anchor."""
    if issue.anchor is not None:
        return issue.anchor
    hint = _bullet_hint_from_issue(issue)
    if not hint:
        return None

    matches: list[IssueAnchor] = []
    for entry_index, entry in enumerate(resume.get("experience") or []):
        for bullet_index, bullet in enumerate(entry.get("bullets") or []):
            if _bullet_hint_matches(str(bullet), hint):
                matches.append(
                    IssueAnchor(
                        section="experience",
                        entry_index=entry_index,
                        bullet_index=bullet_index,
                    )
                )
    for entry_index, entry in enumerate(resume.get("projects") or []):
        for bullet_index, bullet in enumerate(entry.get("bullets") or []):
            if _bullet_hint_matches(str(bullet), hint):
                matches.append(
                    IssueAnchor(
                        section="projects",
                        entry_index=entry_index,
                        bullet_index=bullet_index,
                    )
                )
    for entry_index, entry in enumerate(resume.get("education") or []):
        for bullet_index, bullet in enumerate(entry.get("bullets") or []):
            if _bullet_hint_matches(str(bullet), hint):
                matches.append(
                    IssueAnchor(
                        section="education",
                        entry_index=entry_index,
                        bullet_index=bullet_index,
                    )
                )
    return matches[0] if len(matches) == 1 else None


def enrich_issues_with_inferred_anchors(
    resume: dict[str, Any],
    issues: list[BlockingIssue],
) -> list[BlockingIssue]:
    enriched: list[BlockingIssue] = []
    for issue in issues:
        anchor = infer_anchor_from_issue(resume, issue)
        if anchor is None or issue.anchor is not None:
            enriched.append(issue)
            continue
        enriched.append(issue.model_copy(update={"anchor": anchor}))
    return enriched


def _anchor_in_issues(anchor: IssueAnchor, issues: list[BlockingIssue]) -> bool:
    for issue in issues:
        if issue.anchor is None:
            continue
        if (
            issue.anchor.section == anchor.section
            and issue.anchor.entry_index == anchor.entry_index
            and issue.anchor.bullet_index == anchor.bullet_index
        ):
            return True
    return False


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


def _patch_conflicts_with_anchor(
    resume: dict[str, Any],
    patch: ResumePatch,
    anchor: IssueAnchor,
) -> bool:
    """True when patch names a different company/project than the anchor location."""
    resolved = resolve_bullet_at_anchor(resume, anchor)
    if not resolved:
        return True
    if resolved["section"] == "experience" and patch.section == "experience":
        company = (patch.company or "").strip()
        return bool(company and not _names_match(company, resolved["company"]))
    if resolved["section"] == "projects" and patch.section == "projects":
        project_name = (patch.project_name or "").strip()
        return bool(
            project_name and not _names_match(project_name, resolved["project_name"])
        )
    if resolved["section"] == "education" and patch.section == "education":
        institution = (patch.institution or "").strip()
        return bool(
            institution and not _names_match(institution, resolved["institution"])
        )
    return False


def _patch_content_matches_anchor(
    resume: dict[str, Any],
    patch: ResumePatch,
    anchor: IssueAnchor,
) -> bool:
    """True when patch company/name/bullet_old align with the anchor location."""
    resolved = resolve_bullet_at_anchor(resume, anchor)
    if not resolved:
        return False
    if resolved["section"] == "experience" and patch.section == "experience":
        company = (patch.company or "").strip()
        bullet_old = (patch.bullet_old or "").strip()
        if company and not _names_match(company, resolved["company"]):
            return False
        if bullet_old and not _bullet_hint_matches(resolved["bullet_old"], bullet_old):
            return False
        return True
    if resolved["section"] == "projects" and patch.section == "projects":
        project_name = (patch.project_name or "").strip()
        bullet_old = (patch.project_bullet_old or "").strip()
        if project_name and not _names_match(project_name, resolved["project_name"]):
            return False
        if bullet_old and not _bullet_hint_matches(resolved["project_bullet_old"], bullet_old):
            return False
        return True
    if resolved["section"] == "education" and patch.section == "education":
        institution = (patch.institution or "").strip()
        bullet_old = (patch.education_bullet_old or "").strip()
        if institution and not _names_match(institution, resolved["institution"]):
            return False
        if bullet_old and not _bullet_hint_matches(resolved["education_bullet_old"], bullet_old):
            return False
        return True
    return False


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


def _anchor_for_patch_index(
    resume: dict[str, Any],
    patch: ResumePatch,
    target_issues: list[BlockingIssue],
    patch_index: int,
) -> IssueAnchor | None:
    """Bind a chat patch to its ATS anchor — content match first, guarded positional."""
    anchor = match_anchor_for_patch(resume, patch, target_issues)
    if anchor is not None:
        return anchor

    if patch_index < len(target_issues):
        positional = target_issues[patch_index].anchor
        if positional is not None:
            if len(target_issues) == 1:
                return positional
            if not _patch_conflicts_with_anchor(resume, patch, positional):
                return positional

    if patch.anchor is not None and _anchor_in_issues(patch.anchor, target_issues):
        return patch.anchor
    return None


def hydrate_chat_patches(
    resume: dict[str, Any],
    patches: list[ResumePatch],
    target_issues: list[BlockingIssue],
) -> list[ResumePatch]:
    """Attach anchors and canonical bullet_old to LLM patches."""
    issues = enrich_issues_with_inferred_anchors(resume, target_issues)
    if not any(issue.anchor is not None for issue in issues):
        return patches

    hydrated: list[ResumePatch] = []
    for index, patch in enumerate(patches):
        anchor = _anchor_for_patch_index(resume, patch, issues, index)
        hydrated.append(hydrate_patch_from_anchor(resume, patch, anchor))

    return hydrated
