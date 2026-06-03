from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CoachMessage(BaseModel):
    role: Literal["coach", "user"]
    text: str = Field(..., min_length=1, max_length=2000)


class CoachRequest(BaseModel):
    segment_text: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Transcript of the segment being coached.",
    )
    history: list[CoachMessage] = Field(
        default_factory=list,
        description="Prior coach/user exchanges in this session (max 3 coach turns).",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for credit-dedup / audit.",
    )

    @model_validator(mode="after")
    def validate_exchange_count(self) -> "CoachRequest":
        coach_turns = sum(1 for m in self.history if m.role == "coach")
        if coach_turns > 3:
            raise ValueError("Maximum 3 coaching exchanges per segment session.")
        return self


class InterviewMessage(BaseModel):
    """One turn in a coached interview session."""
    role: Literal["interviewer", "user"]
    text: str = Field(..., min_length=1, max_length=3000)


class InterviewNextRequest(BaseModel):
    """Request the next interview question given current conversation history."""
    history: list[InterviewMessage] = Field(
        default_factory=list,
        description="Full conversation so far (interviewer + user turns).",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for audit / credit-dedup.",
    )

    @model_validator(mode="after")
    def validate_question_count(self) -> "InterviewNextRequest":
        from app.agent.story_interview import MAX_QUESTIONS
        interviewer_turns = sum(1 for m in self.history if m.role == "interviewer")
        if interviewer_turns >= MAX_QUESTIONS:
            raise ValueError(
                f"Maximum {MAX_QUESTIONS} interview questions reached. "
                "Submit your answers to generate the resume."
            )
        return self


class InterviewSubmitRequest(BaseModel):
    """Submit completed interview Q&A to generate a resume."""
    history: list[InterviewMessage] = Field(
        ...,
        min_length=2,
        description="Full conversation (must have at least one Q and one A).",
    )
    whisper_path: bool = Field(
        default=False,
        description="True when Whisper transcription was used for any answer.",
    )

    @model_validator(mode="after")
    def validate_has_user_content(self) -> "InterviewSubmitRequest":
        user_words = sum(
            len(m.text.split()) for m in self.history if m.role == "user"
        )
        if user_words < 30:
            raise ValueError(
                "Interview answers are too short. Please answer at least a few questions "
                "before generating your resume."
            )
        return self


class PolishResumeRequest(BaseModel):
    text: str = Field(..., min_length=50, description="Current resume draft text.")
    instruction: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Plain-English editing instruction, e.g. 'make the summary more senior'.",
    )


class StoryToResumeRequest(BaseModel):
    segments: list[str] = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Transcript text per segment, in recording order.",
    )
    whisper_path: bool = Field(
        default=False,
        description="True when the Whisper transcription path was used (Firefox/Safari). "
                    "Used for credit routing.",
    )

    @model_validator(mode="after")
    def validate_content(self) -> "StoryToResumeRequest":
        total_words = sum(len(s.split()) for s in self.segments)
        if total_words < 50:
            raise ValueError(
                "Story is too short. Please record at least 50 words across all segments."
            )
        return self
