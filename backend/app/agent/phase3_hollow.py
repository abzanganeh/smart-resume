"""Phase 3 hollow-output detection for structured LLM retries."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.rewrite import TailoredResumeOutput


def phase3_total_bullets(output: TailoredResumeOutput) -> int:
    return sum(len(e.bullets) for e in output.experience)


def phase3_is_hollow(output: TailoredResumeOutput) -> bool:
    if not output.experience:
        return True
    if phase3_total_bullets(output) == 0:
        return True
    return False


def reject_hollow_phase3(output: BaseModel) -> str | None:
    if isinstance(output, TailoredResumeOutput) and phase3_is_hollow(output):
        return (
            "Response is hollow: include experience entries with rewritten bullets. "
            "Each entry needs company, title, dates, and at least one bullet."
        )
    return None


__all__ = [
    "phase3_is_hollow",
    "phase3_total_bullets",
    "reject_hollow_phase3",
]
