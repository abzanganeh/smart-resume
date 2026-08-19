"""Suggest job search titles from a master resume."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.services.jobs.preferred_titles import JOB_TITLE_SUGGESTION_COUNT

log = structlog.get_logger("agent.job_title_suggestions")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "job_title_suggestions.txt"

_ADJACENT_BY_KEYWORD: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("react native", "mobile", "ios", "android", "flutter"),
        [
            "Mobile Developer",
            "React Native Developer",
            "Software Engineer Mobile",
            "iOS Developer",
            "Android Developer",
        ],
    ),
    (
        ("python", "django", "fastapi", "flask"),
        [
            "Python Developer",
            "Backend Engineer",
            "Software Engineer Python",
            "Full Stack Engineer",
        ],
    ),
    (
        ("machine learning", "ml", "data science", "pytorch", "tensorflow"),
        [
            "Machine Learning Engineer",
            "Data Scientist",
            "Applied Scientist",
            "ML Engineer",
        ],
    ),
    (
        ("quality", "qa", "test", "sdet"),
        [
            "QA Engineer",
            "Software Development Engineer in Test",
            "Quality Engineer",
            "Test Automation Engineer",
        ],
    ),
]

_GENERIC_TITLES = [
    "Software Engineer",
    "Senior Software Engineer",
    "Full Stack Developer",
    "Backend Engineer",
    "Frontend Engineer",
    "Product Engineer",
    "Technical Lead",
    "Engineering Manager",
]


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def extract_held_titles(parsed_sections: dict[str, Any] | None) -> list[str]:
    """Pull job titles from structured experience sections."""
    if not parsed_sections:
        return []
    experience = parsed_sections.get("experience") or []
    if not isinstance(experience, list):
        return []
    seen: set[str] = set()
    titles: list[str] = []
    for row in experience:
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "").strip()
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        titles.append(title)
    return titles


def _heuristic_suggestions(
    *,
    held_titles: list[str],
    resume_text: str,
    count: int = JOB_TITLE_SUGGESTION_COUNT,
) -> list[str]:
    """Deterministic fallback when LLM is unavailable."""
    blob = resume_text.casefold()
    seen: set[str] = set()
    out: list[str] = []

    def add(title: str) -> None:
        cleaned = title.strip()
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(cleaned)

    for title in held_titles:
        add(title)

    for keywords, candidates in _ADJACENT_BY_KEYWORD:
        if any(kw in blob for kw in keywords):
            for title in candidates:
                add(title)
                if len(out) >= count:
                    return out[:count]

    for title in _GENERIC_TITLES:
        add(title)
        if len(out) >= count:
            break

    return out[:count]


def _parse_llm_titles(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:200])
    return out


async def suggest_job_titles(
    *,
    resume_text: str,
    parsed_sections: dict[str, Any] | None,
    llm_client: LLMClient | None,
    count: int = JOB_TITLE_SUGGESTION_COUNT,
) -> tuple[list[str], list[str], str]:
    """Return (suggestions, held_titles, source).

    ``source`` is ``llm`` or ``heuristic``.
    """
    held = extract_held_titles(parsed_sections)
    trimmed = resume_text.strip()
    if not trimmed and not held:
        return [], [], "heuristic"

    if llm_client is None:
        return _heuristic_suggestions(held_titles=held, resume_text=trimmed, count=count), held, "heuristic"

    held_block = "\n".join(f"- {t}" for t in held) if held else "(none parsed)"
    prompt = (
        _load_prompt()
        .replace("{count}", str(count))
        .replace("{held_titles}", held_block)
        .replace("{resume_text}", trimmed[:12000])
    )

    try:
        response = await llm_client.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            max_tokens=1024,
            temperature=0.3,
        )
        llm_titles = _parse_llm_titles(response.content or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("job_title_suggestions_llm_failed", error=str(exc))
        llm_titles = []

    if len(llm_titles) < count // 2:
        merged = _heuristic_suggestions(held_titles=held, resume_text=trimmed, count=count)
        seen = {t.casefold() for t in llm_titles}
        for title in merged:
            if title.casefold() in seen:
                continue
            llm_titles.append(title)
            seen.add(title.casefold())
            if len(llm_titles) >= count:
                break
        return llm_titles[:count], held, "heuristic"

    # Ensure held titles appear when LLM omitted them
    seen = {t.casefold() for t in llm_titles}
    for title in held:
        if title.casefold() in seen:
            continue
        if len(llm_titles) >= count:
            break
        llm_titles.insert(0, title)
        seen.add(title.casefold())

    return llm_titles[:count], held, "llm"
