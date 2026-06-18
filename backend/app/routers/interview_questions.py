"""Public interview question bank for Flint session enrichment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.limiter import limiter
from app.services.questions.models import InterviewQuestionsResponse
from app.services.questions.service import _load_bank, list_interview_questions

router = APIRouter(tags=["interview-questions"])


@router.get("/api/interview-questions", response_model=InterviewQuestionsResponse)
@limiter.limit("120/minute")
async def get_interview_questions(
    request: Request,
    domain: Annotated[str | None, Query(max_length=120)] = None,
    company: Annotated[str | None, Query(max_length=120)] = None,
    role: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> InterviewQuestionsResponse:
    """Return curated interview questions for Flint digest / question-bank enrichment."""
    del request
    questions = list_interview_questions(
        domain=domain,
        company=company,
        role=role,
        limit=limit,
    )
    return InterviewQuestionsResponse(
        domain=domain,
        company=company,
        role=role,
        questions=questions,
        total=len(questions),
    )


@router.get("/api/interview-questions/stats")
@limiter.limit("60/minute")
async def get_interview_question_stats(request: Request) -> dict[str, int | str]:
    """Return bank statistics for admin/ops visibility (Phase 11.5 read path)."""
    del request
    _load_bank.cache_clear()
    bank = _load_bank()
    by_domain: dict[str, int] = {}
    with_canonical = 0
    for q in bank:
        by_domain[q.domain] = by_domain.get(q.domain, 0) + 1
        if q.canonical_answer:
            with_canonical += 1
    return {
        "total": len(bank),
        "with_canonical_answer": with_canonical,
        "domains": len(by_domain),
        **{f"domain_{k}": v for k, v in sorted(by_domain.items())},
    }
