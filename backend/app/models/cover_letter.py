from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CoverLetterTone = Literal["formal", "balanced", "warm"]


class CoverLetterOutput(BaseModel):
    body_markdown: str
    body_plain: str
    word_count: int = Field(ge=0)
    tone: CoverLetterTone
    keywords_used: list[str] = Field(default_factory=list)
