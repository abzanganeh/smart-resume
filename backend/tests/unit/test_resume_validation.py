"""Unit tests for shared resume text validation."""

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.resume_validation import validate_resume_text


def test_validate_resume_text_strips_and_returns() -> None:
    raw = ("hello world " * 20).strip()
    assert len(raw) >= 200
    assert validate_resume_text(f"  {raw}  ") == raw


def test_validate_resume_text_rejects_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_resume_text("   ")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "resume_empty"


def test_validate_resume_text_rejects_too_short() -> None:
    short = "a" * (settings.MIN_RESUME_CHARS - 1)
    with pytest.raises(HTTPException) as exc:
        validate_resume_text(short)
    assert exc.value.detail["code"] == "resume_too_short"


def test_validate_resume_text_rejects_too_long() -> None:
    long = "x" * (settings.MAX_RESUME_CHARS + 1)
    with pytest.raises(HTTPException) as exc:
        validate_resume_text(long)
    assert exc.value.detail["code"] == "resume_too_long"
