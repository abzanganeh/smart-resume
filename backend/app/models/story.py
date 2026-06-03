from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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
