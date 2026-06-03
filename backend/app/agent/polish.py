"""Apply a targeted plain-English editing instruction to a resume draft.

Used by the Story Mode review step so users can refine the AI-generated
resume via a chat-like interface before saving it to their profile.

No credit is charged: this is a free iteration on a story_build that
already cost 1 credit.
"""
from __future__ import annotations

import structlog

from app.llm.base import LLMClient, LLMMessage

log = structlog.get_logger("agent.polish")

_SYSTEM = """\
You are a professional resume editor.
You will receive a resume in plain text and a single editing instruction.
Apply the instruction precisely and return the complete updated resume.

Rules:
- Return ONLY the updated resume text — no commentary, no markdown fences.
- Preserve all sections that are not affected by the instruction.
- Keep the same plain-text formatting style as the input.
- If the instruction is unclear or not applicable, return the original resume unchanged.
"""


async def polish_resume(
    resume_text: str,
    instruction: str,
    llm_client: LLMClient,
    *,
    max_output_tokens: int = 2000,
) -> str:
    """Return the resume text after applying `instruction`.

    Raises:
        RuntimeError: If the LLM returns an empty response.
    """
    log.info("polish.start", instruction_len=len(instruction), text_len=len(resume_text))

    messages = [
        LLMMessage(role="system", content=_SYSTEM),
        LLMMessage(
            role="user",
            content=(
                f"RESUME:\n{resume_text}\n\n"
                f"INSTRUCTION:\n{instruction}"
            ),
        ),
    ]

    response = await llm_client.complete(messages, max_tokens=max_output_tokens)
    result = response.content.strip() if response and response.content else ""

    if not result:
        raise RuntimeError("polish_resume: LLM returned an empty response.")

    log.info("polish.done", result_len=len(result))
    return result
