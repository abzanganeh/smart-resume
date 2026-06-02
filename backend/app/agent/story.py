"""Convert a raw spoken career narrative to structured resume text.

Step 1 of the story-to-resume pipeline. Step 2 reuses the existing
parse_resume infrastructure.
"""
from __future__ import annotations

import structlog
from pathlib import Path

from app.llm.base import LLMClient, LLMMessage

log = structlog.get_logger("agent.story")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "story_to_resume.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def story_to_resume(
    narrative: str,
    llm_client: LLMClient,
    *,
    max_output_tokens: int = 1500,
) -> str:
    """
    Convert a raw spoken narrative to structured resume draft text.

    Args:
        narrative: Joined transcript from all story segments.
        llm_client: Resolved LLM client (BYOK or platform default).
        max_output_tokens: Cap for output tokens (resume text is ~800 words).

    Returns:
        Plain-text resume draft ready for the existing parse_resume pipeline.

    Raises:
        RuntimeError: If the LLM response is empty or too short to be a resume.
    """
    prompt_template = _load_prompt()
    prompt = prompt_template.replace("{narrative}", narrative)

    log.info("story.convert_start", narrative_chars=len(narrative))

    messages = [
        LLMMessage(role="system", content="You are a professional resume writer."),
        LLMMessage(role="user", content=prompt),
    ]

    response = await llm_client.complete(
        messages,
        max_tokens=max_output_tokens,
    )

    draft = response.content.strip() if response and response.content else ""

    if len(draft) < 100:
        raise RuntimeError(
            f"story_to_resume: LLM returned unexpectedly short output ({len(draft)} chars). "
            "The narrative may be too short or the LLM may have failed."
        )

    log.info("story.convert_done", draft_chars=len(draft))
    return draft
