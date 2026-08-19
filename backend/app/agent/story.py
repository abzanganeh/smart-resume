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

# Gemini 3.x thinking models spend a large share of max_output_tokens on
# hidden reasoning. 1500 was enough to emit the empty format template and
# then hit MAX_TOKENS (~180 chars). Leave room for thoughts + a full resume.
_DEFAULT_MAX_OUTPUT_TOKENS = 8192

_PLACEHOLDER_MARKERS = (
    "[text]",
    "[comma-separated list]",
    "[Company Name]",
    "[Job Title]",
    "[Start Date]",
    "[End Date]",
    "[bullet]",
    "[Institution]",
    "[Degree]",
    "[Year]",
    "[Project Name]",
    "[description]",
    "[tech stack]",
    "[Name]",
    "[Issuer]",
)

_RETRY_INSTRUCTION = (
    "The previous output copied blank template placeholders instead of a resume. "
    "Write the filled resume from the story. Use the section headers. "
    "Do not output square-bracket placeholders."
)


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _is_unfilled_template(draft: str) -> bool:
    """True when the model echoed the format skeleton instead of a resume."""
    hits = sum(1 for marker in _PLACEHOLDER_MARKERS if marker.lower() in draft.lower())
    return hits >= 2


async def story_to_resume(
    narrative: str,
    llm_client: LLMClient,
    *,
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
) -> str:
    """
    Convert a raw spoken narrative to structured resume draft text.

    Args:
        narrative: Joined transcript from all story segments.
        llm_client: Resolved LLM client (BYOK or platform default).
        max_output_tokens: Cap for output tokens. Must be high enough for
            Gemini 3.x thinking plus a full resume.

    Returns:
        Plain-text resume draft ready for the existing parse_resume pipeline.

    Raises:
        RuntimeError: If the LLM response is empty, too short, or still a
            blank template after one retry.
    """
    prompt_template = _load_prompt()
    prompt = prompt_template.replace("{narrative}", narrative)

    log.info("story.convert_start", narrative_chars=len(narrative))

    messages = [
        LLMMessage(role="system", content="You are a professional resume writer."),
        LLMMessage(role="user", content=prompt),
    ]

    draft = ""
    for attempt in (1, 2):
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

        if not _is_unfilled_template(draft):
            log.info("story.convert_done", draft_chars=len(draft), attempt=attempt)
            return draft

        log.warning(
            "story.convert_template_echo",
            draft_chars=len(draft),
            attempt=attempt,
        )
        messages = [
            *messages,
            LLMMessage(role="assistant", content=draft),
            LLMMessage(role="user", content=_RETRY_INSTRUCTION),
        ]

    raise RuntimeError(
        "story_to_resume: model returned an empty template instead of a resume. "
        "Retry generating from your story."
    )
