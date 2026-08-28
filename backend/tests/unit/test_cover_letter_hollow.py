"""Unit tests for cover letter hollow-output rejection."""

from __future__ import annotations

import pytest

from app.agent.cover_letter import _cover_letter_is_hollow, _reject_hollow_cover_letter
from app.models.cover_letter import CoverLetterOutput


def test_cover_letter_is_hollow_when_body_empty() -> None:
    output = CoverLetterOutput(
        body_markdown="",
        body_plain="   ",
        word_count=0,
        tone="balanced",
    )
    assert _cover_letter_is_hollow(output) is True


def test_cover_letter_is_hollow_when_too_short() -> None:
    output = CoverLetterOutput(
        body_markdown="Hi",
        body_plain="Too few words here.",
        word_count=4,
        tone="balanced",
    )
    assert _cover_letter_is_hollow(output) is True


def test_cover_letter_not_hollow_with_substantive_body() -> None:
    body = " ".join(["word"] * 60)
    output = CoverLetterOutput(
        body_markdown=body,
        body_plain=body,
        word_count=60,
        tone="balanced",
    )
    assert _cover_letter_is_hollow(output) is False


def test_reject_hollow_cover_letter_returns_message() -> None:
    output = CoverLetterOutput(
        body_markdown="",
        body_plain="",
        word_count=0,
        tone="balanced",
    )
    message = _reject_hollow_cover_letter(output)
    assert message is not None
    assert "hollow" in message.lower()


def test_reject_hollow_cover_letter_passes_valid() -> None:
    body = " ".join(["word"] * 60)
    output = CoverLetterOutput(
        body_markdown=body,
        body_plain=body,
        word_count=60,
        tone="balanced",
    )
    assert _reject_hollow_cover_letter(output) is None


def test_reject_hollow_cover_letter_blocks_short_body() -> None:
    """Removing accept_result would let vacuous cover letters through."""
    output = CoverLetterOutput(
        body_markdown="Thanks.",
        body_plain="Thanks for your time.",
        word_count=4,
        tone="balanced",
    )
    assert _reject_hollow_cover_letter(output) is not None
