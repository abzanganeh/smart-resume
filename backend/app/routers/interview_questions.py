"""Public interview question bank for Flint session enrichment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.limiter import limiter
from app.services.questions.models import InterviewQuestionsResponse
from app.services.questions.service import list_interview_questions

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
