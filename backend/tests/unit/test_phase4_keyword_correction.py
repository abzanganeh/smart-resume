"""Phase 4 keyword-issue correction logic.

These cases run on the same module-level helpers Phase 4 builds inside
``run`` — extracted here so we can verify behavior without invoking an LLM.
The tests drive the same code paths by re-implementing the small helper
closure with the public utilities exposed from the agent package.
"""

from __future__ import annotations

from app.agent.phase3_postprocess import flatten_skill_terms
from app.models.qa import BlockingIssue, QAOutput


def _correct_issues(
    issues: list[BlockingIssue],
    existing_skills: list[str],
    must_have_terms: list[str],
    full_text_corpus: str,
) -> list[BlockingIssue]:
    """Mirror of the in-function correction logic in ``phase4_qa.run``.

    Kept in sync with the source — change both when the rule changes.
    """
    import re

    flat_skill_terms = flatten_skill_terms(existing_skills)

    def _quoted(text: str) -> list[str]:
        return [
            m.strip()
            for m in re.findall(
                r"['\"\u2018\u2019\u201c\u201d]([^'\"\u2018\u2019\u201c\u201d]{2,80})['\"\u2018\u2019\u201c\u201d]",
                text,
            )
            if m.strip()
        ]

    def _candidates(suggestion: str) -> list[str]:
        terms = _quoted(suggestion)
        lower = suggestion.lower()
        for term in must_have_terms:
            if term and term.lower() in lower and term not in terms:
                terms.append(term)
        return terms

    out: list[BlockingIssue] = []
    for issue in issues:
        if issue.category == "keyword":
            cand = _candidates(issue.suggestion)
            if cand and all(c.lower() in full_text_corpus for c in cand):
                continue
            lower = issue.suggestion.lower()
            if any(p in lower for p in ("skills section", "add to skills", "to skills")):
                already = [t for t in flat_skill_terms if t.lower() in lower]
                if already:
                    issue = issue.model_copy(
                        update={
                            "suggestion": (
                                f"Reinforce {', '.join(already)} in at least one Experience "
                                f"bullet or your Professional Summary — they already appear in "
                                f"your Skills section."
                            )
                        }
                    )
        out.append(issue)
    return out


def _make_issue(suggestion: str) -> BlockingIssue:
    return BlockingIssue(
        category="keyword",
        description="Missing keyword",
        suggestion=suggestion,
        impact="high",
        fix_effort="one_click",
    )


def test_drops_issue_when_unquoted_keyword_already_in_resume() -> None:
    issues = [_make_issue("Add Python to the Skills section")]
    corrected = _correct_issues(
        issues,
        existing_skills=["AI & Machine Learning: Python, LLMs"],
        must_have_terms=["Python"],
        full_text_corpus="ai & machine learning: python, llms",
    )
    assert corrected == []


def test_redirects_skills_suggestion_when_keyword_inside_category_line() -> None:
    issues = [_make_issue("Add Kubernetes to Skills")]
    corrected = _correct_issues(
        issues,
        existing_skills=["DevOps: Kubernetes, Docker"],
        must_have_terms=[],
        full_text_corpus="devops: kubernetes, docker",
    )
    assert len(corrected) == 1
    assert "Reinforce Kubernetes" in corrected[0].suggestion
    assert "Experience bullet" in corrected[0].suggestion


def test_keeps_issue_when_keyword_is_genuinely_missing() -> None:
    issues = [_make_issue("Add 'GraphQL' to Skills")]
    corrected = _correct_issues(
        issues,
        existing_skills=["Programming: Python, FastAPI"],
        must_have_terms=["GraphQL"],
        full_text_corpus="programming: python, fastapi",
    )
    assert len(corrected) == 1
    assert corrected[0].suggestion == "Add 'GraphQL' to Skills"
