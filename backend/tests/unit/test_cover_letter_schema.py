"""Pydantic validation for CoverLetterOutput."""

from app.models.cover_letter import CoverLetterOutput


def test_cover_letter_output_accepts_valid_payload() -> None:
    out = CoverLetterOutput.model_validate(
        {
            "body_markdown": "Dear team,\n\nI am a strong fit.\n",
            "body_plain": "Dear team,\n\nI am a strong fit.\n",
            "word_count": 6,
            "tone": "warm",
            "keywords_used": ["Python", "FastAPI"],
        }
    )
    assert out.tone == "warm"
    assert out.word_count == 6
    assert len(out.keywords_used) == 2
