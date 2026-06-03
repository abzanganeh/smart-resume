"""AI-driven interview conductor for Coached Story Mode.

Asks structured career questions one at a time, optionally follows up
when an answer is vague, and signals completion when all key topics are
covered.  The caller drives the exchange loop and enforces credit limits.
"""
from __future__ import annotations

import structlog
from pathlib import Path
from typing import AsyncGenerator

from app.llm.base import LLMClient, LLMMessage

log = structlog.get_logger("agent.story_interview")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "interview_questions.txt"
_COMPLETE_SENTINEL = "INTERVIEW_COMPLETE"

# Soft cap — the endpoint enforces this too, but having it here prevents
# runaway credit use in the unlikely event of a loop bug.
MAX_QUESTIONS = 15


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_history_text(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no prior exchanges — this is the first question)"
    lines = []
    for msg in history:
        role = msg.get("role", "unknown").capitalize()
        text = msg.get("text", "")
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


async def next_interview_question(
    history: list[dict[str, str]],
    llm_client: LLMClient,
) -> AsyncGenerator[str, None]:
    """Stream the next interview question based on conversation history.

    Yields text deltas.  When the LLM emits ``INTERVIEW_COMPLETE`` the
    caller should stop the session and submit all answers.

    Args:
        history: List of {"role": "interviewer"|"user", "text": str} dicts.
        llm_client: Resolved LLM client (always cheapest available model).
    """
    prompt_template = _load_prompt()
    history_text = _build_history_text(history)
    prompt = prompt_template.replace("{history}", history_text)

    question_n = sum(1 for m in history if m.get("role") == "interviewer") + 1
    log.info("story_interview.next_question", question_n=question_n)

    messages = [
        LLMMessage(
            role="system",
            content="You are a professional career interview coach. Ask one concise question.",
        ),
        LLMMessage(role="user", content=prompt),
    ]

    accumulated = ""
    async for delta in llm_client.stream(messages, max_tokens=60):
        accumulated += delta
        yield delta

    is_done = accumulated.strip() == _COMPLETE_SENTINEL
    log.info(
        "story_interview.question_done",
        chars=len(accumulated),
        interview_complete=is_done,
    )


def is_interview_complete(text: str) -> bool:
    """Return True if the LLM signalled the interview is finished."""
    return text.strip() == _COMPLETE_SENTINEL


def compile_answers_to_narrative(history: list[dict[str, str]]) -> str:
    """Join all user answers into a single narrative for the from-story pipeline.

    The interviewer questions become light context; user answers are the
    primary content.  Format: Q: … / A: … blocks, one per exchange.
    """
    pairs: list[str] = []
    buffer_q: str | None = None

    for msg in history:
        role = msg.get("role")
        text = msg.get("text", "").strip()
        if role == "interviewer":
            buffer_q = text
        elif role == "user" and buffer_q:
            pairs.append(f"Q: {buffer_q}\nA: {text}")
            buffer_q = None
        elif role == "user":
            # Answer without a preceding question (shouldn't happen, but handle it)
            pairs.append(f"A: {text}")

    return "\n\n".join(pairs)
