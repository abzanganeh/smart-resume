"""Shared resume text validation for upload and paste endpoints."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.config import settings


def validate_resume_text(raw: str) -> str:
    """Strip and enforce min/max length for resume body text."""
    text = raw.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "resume_empty",
                "message": "Resume is empty — upload a file or paste your resume text.",
            },
        )
    if len(text) < settings.MIN_RESUME_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "resume_too_short",
                "message": (
                    f"Resume is too short ({len(text)} characters). "
                    f"Provide at least {settings.MIN_RESUME_CHARS} characters of resume content."
                ),
            },
        )
    if len(text) > settings.MAX_RESUME_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "resume_too_long",
                "message": (
                    f"Resume exceeds {settings.MAX_RESUME_CHARS:,} characters. "
                    "Trim older or irrelevant experience."
                ),
            },
        )
    return text
