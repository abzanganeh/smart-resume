"""LLM-backed suggestions for Phase 2 audit bullet fixes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.audit import BulletIssue
from app.models.session import Session


class BulletFixSuggestionItem(BaseModel):
    index: int
    suggestion: str


class BulletFixSuggestionsOutput(BaseModel):
    fixes: list[BulletFixSuggestionItem] = Field(default_factory=list)


_SYSTEM = (
    "You rewrite resume bullets for a job-tailoring app. "
    "Each fix must start with a strong action verb, include a metric when the "
    "original implies one (never invent numbers), remove clichés, and align with "
    "the job description. Return only the rewritten bullet text — no quotes or labels."
)


async def suggest_bullet_fixes(
    llm: LLMClient,
    *,
    session: Session,
    issues: list[BulletIssue],
    indices: list[int],
) -> list[BulletFixSuggestionItem]:
    """Generate corrected bullets for the selected audit issue indices."""
    if not issues:
        return []

    selected: list[tuple[int, BulletIssue]] = []
    for idx in indices:
        if 0 <= idx < len(issues):
            selected.append((idx, issues[idx]))
    if not selected:
        return []

    jd_excerpt = (session.jd_raw or "")[:4000]
    lines = [
        "Rewrite each bullet below. Preserve factual content; improve clarity and JD alignment.",
        "",
        f"JOB DESCRIPTION (excerpt):\n{jd_excerpt}",
        "",
        "BULLETS TO FIX:",
    ]
    for idx, issue in selected:
        flags = ", ".join(issue.issues) if issue.issues else "weak bullet"
        lines.append(f"[index={idx}] section={issue.section!r} flags={flags}")
        lines.append(f"original: {issue.original}")
        if issue.missing_keywords:
            lines.append(f"missing_keywords: {', '.join(issue.missing_keywords)}")
        lines.append("")

    user_prompt = "\n".join(lines)
    result = await complete_structured(
        llm,
        messages=[
            LLMMessage(role="system", content=_SYSTEM),
            LLMMessage(role="user", content=user_prompt),
        ],
        schema=BulletFixSuggestionsOutput,
    )
    allowed = {idx for idx, _ in selected}
    return [fix for fix in result.fixes if fix.index in allowed and fix.suggestion.strip()]
