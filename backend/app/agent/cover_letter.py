from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import structlog
from pydantic import BaseModel

from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import LLMParseError, complete_structured
from app.models.cover_letter import CoverLetterOutput, CoverLetterTone
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_COVER_LETTER = (Path(__file__).parent / "prompts" / "cover_letter.txt").read_text()


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _cover_letter_is_hollow(output: CoverLetterOutput) -> bool:
    body = output.body_plain.strip()
    if not body:
        return True
    return _word_count(body) < 50


def _reject_hollow_cover_letter(output: BaseModel) -> str | None:
    if isinstance(output, CoverLetterOutput) and _cover_letter_is_hollow(output):
        return (
            "Cover letter body is hollow: provide body_plain with at least 50 words "
            "of substantive content tailored to the job."
        )
    return None


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
    *,
    tone: CoverLetterTone = "balanced",
    custom_hook: str | None = None,
) -> CoverLetterOutput:
    await event_queue.put({
        "event": "progress",
        "message": "Drafting cover letter…",
    })

    if not session.phase3_output:
        raise RuntimeError("Phase 3 must complete before generating a cover letter.")

    tailored = session.phase3_output
    user_info = session.user_info
    jd_text = session.jd_raw or ""
    target_role = user_info.target_role if user_info else ""
    candidate_name = user_info.name if user_info else ""
    hook_block = f"\nCUSTOM HOOK (use or adapt):\n{custom_hook}\n" if custom_hook else ""

    must_have = (
        [k.term for k in session.phase1_output.must_have_keywords]
        if session.phase1_output
        else []
    )

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _COVER_LETTER),
        LLMMessage(
            role="user",
            content=(
                f"TONE: {tone}\n"
                f"CANDIDATE NAME: {candidate_name}\n"
                f"TARGET ROLE: {target_role}\n"
                f"{hook_block}\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"MUST-HAVE KEYWORDS:\n{json.dumps(must_have)}\n\n"
                f"TAILORED RESUME:\n{tailored.model_dump_json()}\n\n"
                f"USER INFO:\n{user_info.model_dump_json() if user_info else '{}'}\n"
            ),
        ),
    ]

    try:
        output = await complete_structured(
            llm,
            messages,
            CoverLetterOutput,
            max_tokens=2500,
            accept_result=_reject_hollow_cover_letter,
        )
    except (LLMParseError, ValueError) as exc:
        raise RuntimeError(
            "Cover letter generation failed: model returned hollow or invalid output "
            "after retries. Try a different step pin or retry."
        ) from exc

    if _cover_letter_is_hollow(output):
        raise RuntimeError(
            "Cover letter generation failed: model returned hollow output after retries."
        )

    if output.word_count <= 0 and output.body_plain.strip():
        output = output.model_copy(update={"word_count": _word_count(output.body_plain)})

    await event_queue.put({
        "event": "partial",
        "data": json.loads(output.model_dump_json()),
    })
    log.info(
        "cover_letter_done",
        tone=output.tone,
        word_count=output.word_count,
        keywords=len(output.keywords_used),
    )
    return output
