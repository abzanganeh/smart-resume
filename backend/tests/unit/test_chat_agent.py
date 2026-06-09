"""Unit tests for resume chat agent prompt assembly."""

from __future__ import annotations

import json

from app.agent.chat import _SYSTEM_PROMPT


def test_chat_prompt_can_include_json_examples_without_format_error() -> None:
    """Prompt must not use str.format placeholders beyond resume_json/jd_text."""
    resume_json = json.dumps({"projects": []})
    jd_text = "About the role"
    rendered = _SYSTEM_PROMPT.replace("{resume_json}", resume_json).replace("{jd_text}", jd_text)
    assert resume_json in rendered
    assert jd_text in rendered
    assert "new_project" in rendered
