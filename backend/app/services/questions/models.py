"""Pydantic models for the interview question bank API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    id: str
    text: str
    domain: str
    category: str
    canonical_answer: str | None = None


class InterviewQuestionsResponse(BaseModel):
    domain: str | None = None
    company: str | None = None
    role: str | None = None
    questions: list[InterviewQuestion] = Field(default_factory=list)
    total: int = 0
