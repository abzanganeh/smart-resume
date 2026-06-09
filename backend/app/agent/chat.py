"""Resume chat agent — targeted patch generation from free-form user requests."""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured
from app.models.chat import ChatMessage, ChatRequest, ChatResponse
from app.models.session import Session

log = structlog.get_logger("chat_agent")

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "chat.txt").read_text()


async def run(
    session: Session,
    request: ChatRequest,
    llm: LLMClient,
) -> ChatResponse:
    """Generate a conversational reply and optional resume patches for the user's message."""

    if session.phase3_output is None:
        return ChatResponse(
            reply="No tailored resume exists yet. Please run the Tailored Rewrite phase first, then come back here to make targeted edits.",
            patches=[],
        )

    resume_json = json.dumps(session.phase3_output.model_dump(), indent=2)
    jd_text = session.jd_raw or ""

    # Use replace(), not str.format() — the prompt may contain JSON examples with braces.
    system_content = (
        _SYSTEM_PROMPT.replace("{resume_json}", resume_json).replace("{jd_text}", jd_text)
    )

    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=system_content),
        *[LLMMessage(role=m.role, content=m.content) for m in request.history],
        LLMMessage(role="user", content=request.message),
    ]

    try:
        return await complete_structured(llm, messages, ChatResponse, max_tokens=2000, temperature=0.3)
    except Exception as exc:
        log.warning("chat_agent_error", error=str(exc))
        return ChatResponse(
            reply="I had trouble processing that request. Could you rephrase or be more specific about which part of the resume to change?",
            patches=[],
        )
