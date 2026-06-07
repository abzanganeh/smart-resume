"""Cheap-model extraction of company intelligence from JD text.

Model selection (never uses user BYOK keys — platform keys only):

  Primary:  gemini / gemini-2.5-flash-lite  ($0.0375/$0.15 per 1M tokens)
  Fallback: openai / gpt-4o-mini            ($0.15/$0.60 per 1M tokens)

If neither platform key is configured the function returns None so Phase 3
runs unchanged rather than raising.

The extraction happens against the JD text alone — no web scraping.  Most
JDs contain "About Us", "Our Mission", "Our Values", or "Why Join Us"
sections that provide all the signal we need.  This avoids HTTP latency,
scraping failures, and robots.txt issues entirely.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from typing import Any

from app.llm.base import LLMClient, LLMMessage
from app.llm.pricing import estimate_cost, format_cost
from app.models.company_profile import CompanyIntelOutput

log = structlog.get_logger("company_intel.extractor")

_PROMPT = (Path(__file__).parent.parent.parent / "agent" / "prompts" / "company_intel_extraction.txt").read_text()

# Hard cap on JD chars sent to the extractor — keeps token cost bounded.
# 12 000 chars ≈ 4 000 tokens (gemini-2.5-flash-lite input budget: fine).
_JD_CHAR_LIMIT = 12_000

_PRIMARY_MODEL = "gemini-2.5-flash-lite"
_FALLBACK_MODEL = "gpt-4o-mini"

# JSON field names expected in the LLM response.
_EXPECTED_KEYS = frozenset({"mission", "values", "culture_notes"})

# Prevents a crafted company name (from the user-supplied JD) from injecting
# fake instructions into the extraction prompt.
_COMPANY_NAME_MAX_CHARS = 200


def _sanitize_company_name(name: str) -> str:
    """Return a single-line, length-capped company name safe for prompt injection."""
    # Take only the first line to strip any embedded newlines.
    single_line = name.splitlines()[0] if name.strip() else name
    return single_line.strip()[:_COMPANY_NAME_MAX_CHARS]


def _get_extraction_client() -> LLMClient | None:
    """Return the cheapest available platform LLM client for extraction.

    Returns None when no platform key is configured so the caller can
    skip extraction gracefully.
    """
    from app.config import settings
    from app.llm.factory import _is_real_api_key  # noqa: PLC2701 — shared key validation

    if _is_real_api_key(settings.GOOGLE_API_KEY):
        from app.llm.providers.gemini_adapter import GeminiAdapter
        return GeminiAdapter(model=_PRIMARY_MODEL, api_key=settings.GOOGLE_API_KEY)

    if _is_real_api_key(settings.OPENAI_API_KEY):
        from app.llm.providers.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(model=_FALLBACK_MODEL, api_key=settings.OPENAI_API_KEY)

    return None


def _parse_json_from_response(raw: str) -> dict[str, Any] | None:
    """Extract the JSON object from the LLM response, tolerating prose wrappers."""
    # Try direct parse first.
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Fall back to extracting the first {...} block.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


# Per-field char caps prevent verbose LLM output from bloating the Flint
# context window. Combined limit is ~1 400 chars, well within the digest
# LLM's budget alongside a typical JD.
_MISSION_MAX_CHARS = 400
_CULTURE_MAX_CHARS = 400
_VALUE_MAX_CHARS = 80


def _build_intel(company_name: str, data: dict) -> CompanyIntelOutput:
    mission = str(data.get("mission") or "").strip()[:_MISSION_MAX_CHARS]
    raw_values = data.get("values") or []
    if not isinstance(raw_values, list):
        raw_values = []
    values = [str(v).strip()[:_VALUE_MAX_CHARS] for v in raw_values if str(v).strip()][:8]
    culture_notes = str(data.get("culture_notes") or "").strip()[:_CULTURE_MAX_CHARS]
    return CompanyIntelOutput(
        company_name=company_name,
        mission=mission,
        values=values,
        culture_notes=culture_notes,
        source="jd_text",
    )


async def extract_from_jd(
    company_name: str,
    jd_text: str,
) -> CompanyIntelOutput | None:
    """Run cheap-model extraction on JD text.

    Returns None on any failure so callers can degrade gracefully.
    """
    if not (jd_text or "").strip():
        return None

    from app.llm.factory import has_platform_extraction_key
    if not has_platform_extraction_key():
        log.info(
            "company_intel_no_platform_key",
            company_name=company_name,
            hint="configure GOOGLE_API_KEY or OPENAI_API_KEY for company intel extraction",
        )
        return None

    llm = _get_extraction_client()
    if llm is None:
        return None

    safe_name = _sanitize_company_name(company_name)
    jd_truncated = jd_text[:_JD_CHAR_LIMIT]
    user_content = (
        f"COMPANY NAME: {safe_name}\n\n"
        f"JOB DESCRIPTION:\n{jd_truncated}"
    )

    messages = [
        LLMMessage(role="system", content=_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    input_tokens = (len(_PROMPT) + len(user_content)) // 3
    estimated_cost = estimate_cost(input_tokens, 200, llm.provider_name, llm.model_name)
    log.info(
        "company_intel_extraction_start",
        company_name=company_name,
        provider=llm.provider_name,
        model=llm.model_name,
        estimated_cost=format_cost(estimated_cost),
    )

    try:
        raw = await llm.complete(messages, max_tokens=400, temperature=0.0)
    except Exception as exc:
        log.warning("company_intel_llm_error", company_name=company_name, error=str(exc))
        return None

    data = _parse_json_from_response(raw)
    if data is None or not _EXPECTED_KEYS.intersection(data.keys()):
        # raw_preview intentionally omitted — it could echo fragments of the user JD.
        log.warning(
            "company_intel_parse_failed",
            company_name=company_name,
        )
        return None

    intel = _build_intel(company_name, data)
    log.info(
        "company_intel_extraction_complete",
        company_name=company_name,
        has_mission=bool(intel.mission),
        value_count=len(intel.values),
        has_culture=bool(intel.culture_notes),
    )
    return intel
