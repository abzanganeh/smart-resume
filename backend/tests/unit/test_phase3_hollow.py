"""Unit tests for Phase 3 hollow-output detection."""

from __future__ import annotations

from app.agent.phase3_hollow import (
    phase3_is_hollow,
    phase3_total_bullets,
    reject_hollow_phase3,
)
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput


def test_phase3_total_bullets_counts_all_entries() -> None:
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(company="A", bullets=["one", "two"]),
            TailoredExperienceEntry(company="B", bullets=["three"]),
        ]
    )
    assert phase3_total_bullets(output) == 3


def test_phase3_is_hollow_when_no_experience() -> None:
    assert phase3_is_hollow(TailoredResumeOutput(summary="Strong engineer.")) is True


def test_phase3_is_hollow_when_zero_bullets() -> None:
    output = TailoredResumeOutput(
        experience=[TailoredExperienceEntry(company="Acme", title="Engineer", bullets=[])]
    )
    assert phase3_is_hollow(output) is True


def test_phase3_is_hollow_false_when_bullets_present() -> None:
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                company="Acme",
                title="Engineer",
                bullets=["Built platform services."],
            )
        ]
    )
    assert phase3_is_hollow(output) is False


def test_reject_hollow_phase3_returns_message_for_hollow_output() -> None:
    hollow = TailoredResumeOutput(summary="Only a summary.")
    message = reject_hollow_phase3(hollow)
    assert message is not None
    assert "hollow" in message.lower()


def test_reject_hollow_phase3_passes_valid_output() -> None:
    valid = TailoredResumeOutput(
        experience=[TailoredExperienceEntry(company="Acme", bullets=["Did work."])]
    )
    assert reject_hollow_phase3(valid) is None


def test_reject_hollow_phase3_required_for_hollow_detection() -> None:
    """Fails if accept_result hook is removed — hollow summary-only must not pass."""
    hollow = TailoredResumeOutput(summary="Summary only, no experience.")
    assert reject_hollow_phase3(hollow) is not None
