"""Resume chat agent — targeted patch generation from free-form user requests."""
from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.chat import ChatMessage, ChatRequest, ChatResponse, ResumePatch
from app.models.session import Session

log = structlog.get_logger("chat_agent")

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "chat.txt").read_text()


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _names_match(a: str, b: str) -> bool:
    left = _normalize_name(a)
    right = _normalize_name(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _patch_project_name(patch: ResumePatch) -> str | None:
    if patch.section != "projects":
        return None
    if patch.project_name and patch.project_name.strip():
        return patch.project_name.strip()
    if patch.new_project and patch.new_project.name.strip():
        return patch.new_project.name.strip()
    return None


def _infer_target_projects(message: str, project_names: list[str]) -> list[str] | None:
    """When the user clearly names one or more projects, constrain patches to those targets."""

    explicit = [
        m.strip()
        for m in re.findall(r"Project\s*[—–-]\s*(.+?)(?:\n|$)", message, flags=re.I | re.M)
        if m.strip()
    ]
    if explicit:
        return explicit

    hits = [name for name in project_names if name.lower() in message.lower()]
    if len(hits) == 1:
        return hits
    return None


def _filter_patches_to_message_targets(
    patches: list[ResumePatch],
    message: str,
    project_names: list[str],
) -> list[ResumePatch]:
    targets = _infer_target_projects(message, project_names)
    if not targets:
        return patches

    filtered: list[ResumePatch] = []
    for patch in patches:
        pname = _patch_project_name(patch)
        if pname is None:
            if patch.section != "projects":
                filtered.append(patch)
            continue
        if any(_names_match(pname, target) for target in targets):
            filtered.append(patch)
    return filtered


def _synthesize_description(patch: ResumePatch) -> str:
    """Best-effort label when the LLM omits the patch description.

    The UI surfaces this string in the inline "Suggested change" badge, so we
    fall back to a short verb phrase derived from the patch fields rather than
    leaving the user with an empty bubble.
    """

    section = patch.section
    if section == "summary" and patch.new_summary:
        return "Rewrite summary"
    if section == "skills":
        added = ", ".join(patch.add_skills[:3])
        removed = ", ".join(patch.remove_skills[:3])
        if added and removed:
            return f"Add {added}; remove {removed}"
        if added:
            return f"Add skills: {added}"
        if removed:
            return f"Remove skills: {removed}"
    if section == "experience":
        if patch.delete_experience and patch.company:
            return f"Remove {patch.company} entry"
        if patch.bullet_old and patch.bullet_new:
            return f"Rewrite a bullet at {patch.company or 'experience'}"
        if patch.new_title:
            return f"Update title at {patch.company or 'experience'}"
        if patch.new_dates:
            return f"Update dates at {patch.company or 'experience'}"
    if section == "projects":
        if patch.new_project:
            return f"Add project: {patch.new_project.name}"
        if patch.remove_projects:
            return f"Remove project: {patch.remove_projects[0]}"
        if patch.new_project_title and patch.project_name:
            return f"Shorten project title: {patch.project_name} → {patch.new_project_title}"
        if patch.new_project_description is not None and patch.project_name:
            return f"Update project subtitle for {patch.project_name}"
        if patch.project_bullets_replace_all and patch.project_name:
            return f"Rewrite bullets in {patch.project_name}"
        if patch.project_bullet_old and patch.project_name:
            return f"Rewrite a bullet in {patch.project_name}"
    if section == "education":
        if patch.new_institution:
            return f"Rename institution to {patch.new_institution}"
        if patch.add_education_bullets:
            return "Add education bullet"
    if section == "certifications":
        if patch.add_certifications:
            return f"Add: {patch.add_certifications[0]}"
        if patch.remove_certifications:
            return f"Remove: {patch.remove_certifications[0]}"
    if section == "contact" and patch.new_name:
        return f"Update name to {patch.new_name}"
    return f"Update {section}"


def _fill_missing_descriptions(response: ChatResponse) -> ChatResponse:
    """Mutate patches in place so every one has a non-empty description."""

    for patch in response.patches:
        if not patch.description.strip():
            patch.description = _synthesize_description(patch)
    return response


async def run(
    session: Session,
    request: ChatRequest,
    llm: LLMClient,
) -> ChatResponse:
    """Generate a conversational reply and optional resume patches for the user's message."""

    if session.phase3_output is None and not request.tailored_snapshot:
        return ChatResponse(
            reply="No tailored resume exists yet. Please run the Tailored Rewrite phase first, then come back here to make targeted edits.",
            patches=[],
        )

    if request.tailored_snapshot:
        resume_data = request.tailored_snapshot
    else:
        resume_data = session.phase3_output.model_dump()

    resume_json = json.dumps(resume_data, indent=2)
    project_names = [
        str(p.get("name", "")).strip()
        for p in (resume_data.get("projects") or [])
        if str(p.get("name", "")).strip()
    ]
    jd_text = session.jd_raw or ""

    # Inject Phase 4 QA results when available so the agent can answer
    # "what's missing" questions precisely without re-deriving them.
    qa_context = ""
    if session.phase4_output:
        qa = session.phase4_output
        issue_lines = [
            f"- [{i.category}] {i.description} | Fix: {i.suggestion}"
            for i in qa.blocking_issues[:6]
        ]
        qa_context = (
            f"\nCURRENT ATS SCORE: {qa.ats_score}/100 (ceiling: {qa.score_ceiling}/100)\n"
            f"BLOCKING ISSUES (from last QA run — use these to answer ATS improvement questions):\n"
            + ("\n".join(issue_lines) if issue_lines else "  (none)")
        )

    # Use replace(), not str.format() — the prompt may contain JSON examples with braces.
    system_content = (
        _SYSTEM_PROMPT
        .replace("{resume_json}", resume_json)
        .replace("{jd_text}", jd_text)
        .replace("{qa_context}", qa_context)
    )

    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=system_content),
        *[LLMMessage(role=m.role, content=m.content) for m in request.history],
        LLMMessage(
            role="user",
            content=(
                "[Latest request — emit patches ONLY for this message, not prior chat turns]\n"
                f"{request.message}"
            ),
        ),
    ]

    try:
        result = await complete_structured(
            llm, messages, ChatResponse, max_tokens=4000, temperature=0.3
        )
        result.patches = _filter_patches_to_message_targets(
            result.patches,
            request.message,
            project_names,
        )
        return _fill_missing_descriptions(result)
    except Exception as exc:
        log.warning("chat_agent_error", error=str(exc))
        return ChatResponse(
            reply="I had trouble processing that request. Could you rephrase or be more specific about which part of the resume to change?",
            patches=[],
        )
