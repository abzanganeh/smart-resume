"""Mechanical one-click fixes without an LLM round-trip."""

import re

from app.agent.phase3_postprocess import flatten_skill_terms
from app.models.qa import BlockingIssue
from app.models.rewrite import TailoredResumeOutput

_KEYWORD_RE = re.compile(
    r"Add ['\"\u2018\u2019\u201c\u201d]([^'\"\u2018\u2019\u201c\u201d]{1,80})['\"\u2018\u2019\u201c\u201d] to the Skills",
    re.IGNORECASE,
)


def extract_missing_keyword(issue: BlockingIssue) -> str | None:
    if issue.category != "keyword" or issue.fix_effort != "one_click":
        return None
    match = _KEYWORD_RE.search(issue.suggestion)
    if not match:
        return None
    return match.group(1).strip()


def apply_keyword_to_skills(tailored: TailoredResumeOutput, keyword: str) -> TailoredResumeOutput | None:
    term = keyword.strip()
    if not term:
        return None
    flat = {t.lower() for t in flatten_skill_terms(tailored.skills or [])}
    if term.lower() in flat:
        return None

    skills = list(tailored.skills or [])
    if skills:
        first = skills[0]
        if ":" in first:
            prefix, rest = first.split(":", 1)
            items = [item.strip() for item in rest.split(",") if item.strip()]
            items.append(term)
            skills[0] = f"{prefix}: {', '.join(items)}"
        else:
            skills.append(term)
    else:
        skills = [f"Skills: {term}"]

    return tailored.model_copy(update={"skills": skills})
