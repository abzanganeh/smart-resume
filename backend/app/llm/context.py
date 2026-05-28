from __future__ import annotations

from app.llm.base import LLMClient, LLMMessage

CHARS_PER_TOKEN = 3  # conservative estimate


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def fits_in_context(client: LLMClient, messages: list[LLMMessage], reserve_tokens: int = 2048) -> bool:
    total = sum(estimate_tokens(m.content) for m in messages)
    return total + reserve_tokens < client.context_window


def truncate_to_fit(
    client: LLMClient,
    resume_text: str,
    jd_text: str,
    system_overhead: int = 1000,
) -> tuple[str, str]:
    """
    Trim inputs so they fit in the model's context window.
    Rules (from SYSTEM_DESIGN.md):
    - Never truncate the most recent job or the Skills section.
    - Truncate JD to first 3000 tokens before truncating resume.
    - Summarize older experience entries if resume is still too long.
    """
    budget = client.context_window - system_overhead - 2048  # reserve for output
    jd_token_limit = 3000
    jd_char_limit = jd_token_limit * CHARS_PER_TOKEN

    if estimate_tokens(jd_text) > jd_token_limit:
        jd_text = jd_text[: jd_char_limit] + "\n[JD truncated — requirements section preserved]"

    resume_budget_chars = (budget - estimate_tokens(jd_text)) * CHARS_PER_TOKEN
    if len(resume_text) > resume_budget_chars:
        resume_text = resume_text[:resume_budget_chars] + "\n[Resume truncated — older experience removed]"

    return resume_text, jd_text
