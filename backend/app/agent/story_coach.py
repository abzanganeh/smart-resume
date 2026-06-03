"""AI interview coach for Story Mode segments.

Streams one targeted follow-up question per exchange, asking the user
to quantify or clarify their experience.  Max 3 exchanges per segment
session (enforced by the caller / quota layer).
"""
from __future__ import annotations

import structlog
from pathlib import Path
from typing import AsyncGenerator

from app.llm.base import LLMClient, LLMMessage

log = structlog.get_logger("agent.story_coach")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "story_coach.txt"
_COMPLETE_SENTINEL = "COMPLETE:"

MAX_EXCHANGES = 3


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_history_text(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no prior exchanges)"
    lines = []
    for msg in history:
        role = msg.get("role", "unknown").capitalize()
        text = msg.get("text", "")
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


async def coach_segment(
    segment_text: str,
    history: list[dict[str, str]],
    llm_client: LLMClient,
) -> AsyncGenerator[str, None]:
    """Stream one coaching question for the given segment and conversation history.

    Yields text deltas.  Raises ``StopAsyncIteration`` when done.
    The caller is responsible for enforcing MAX_EXCHANGES (3 per segment session).

    Args:
        segment_text: The transcript of the segment being coached.
        history: Prior exchanges, list of {"role": "coach"|"user", "text": str}.
        llm_client: Resolved LLM client (always uses cheapest model available).
    """
    prompt_template = _load_prompt()
    history_text = _build_history_text(history)
    prompt = (
        prompt_template
        .replace("{segment_text}", segment_text.strip())
        .replace("{history}", history_text)
    )

    log.info(
        "story_coach.start",
        segment_chars=len(segment_text),
        exchange_n=len([m for m in history if m.get("role") == "coach"]) + 1,
    )

    messages = [
        LLMMessage(
            role="system",
            content="You are a concise career interview coach. Ask one short follow-up question.",
        ),
        LLMMessage(role="user", content=prompt),
    ]

    accumulated = ""
    async for delta in llm_client.stream(messages, max_tokens=80):
        accumulated += delta
        yield delta

    is_complete = accumulated.strip().startswith(_COMPLETE_SENTINEL)
    log.info(
        "story_coach.done",
        chars=len(accumulated),
        is_complete_segment=is_complete,
    )


def is_complete_response(text: str) -> bool:
    """Return True if the coach determined the segment needs no follow-up."""
    return text.strip().startswith(_COMPLETE_SENTINEL)
