"""Resume chat agent — targeted patch generation from free-form user requests."""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.chat import ChatMessage, ChatRequest, ChatResponse, ResumePatch
from app.models.session import Session

log = structlog.get_logger("chat_agent")

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "chat.txt").read_text()


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

    if session.phase3_output is None:
        return ChatResponse(
            reply="No tailored resume exists yet. Please run the Tailored Rewrite phase first, then come back here to make targeted edits.",
            patches=[],
        )

    resume_json = json.dumps(session.phase3_output.model_dump(), indent=2)
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
        LLMMessage(role="user", content=request.message),
    ]

    try:
        result = await complete_structured(
            llm, messages, ChatResponse, max_tokens=4000, temperature=0.3
        )
        return _fill_missing_descriptions(result)
    except Exception as exc:
        log.warning("chat_agent_error", error=str(exc))
        return ChatResponse(
            reply="I had trouble processing that request. Could you rephrase or be more specific about which part of the resume to change?",
            patches=[],
        )
