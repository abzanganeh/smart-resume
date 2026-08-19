"""Unit tests for agent/story.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.story import _is_unfilled_template, story_to_resume

MOCK_DRAFT = """
PROFESSIONAL SUMMARY
Experienced software engineer with 5 years in ML infrastructure.

SKILLS
Python, AWS, TensorFlow

EXPERIENCE
SecureAuth | Senior Engineer | 2022 – 2025
• Built anomaly detection pipelines
"""

EMPTY_TEMPLATE = """
PROFESSIONAL SUMMARY
[text]

SKILLS
[comma-separated list]

EXPERIENCE
[Company Name] | [Job Title] | [Start Date] – [End Date]
• [bullet]
• [bullet]

EDUCATION
"""


@pytest.mark.asyncio
async def test_story_to_resume_calls_llm():
    """story_to_resume passes joined narrative to LLM and returns its output."""
    mock_response = MagicMock()
    mock_response.content = MOCK_DRAFT

    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=mock_response)

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        result = await story_to_resume("I worked at SecureAuth for three years.", mock_client)

    assert "PROFESSIONAL SUMMARY" in result
    mock_client.complete.assert_called_once()
    call_args = mock_client.complete.call_args
    assert "I worked at SecureAuth" in str(call_args)
    assert call_args.kwargs["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_story_to_resume_raises_on_empty_llm_output():
    """story_to_resume raises RuntimeError when LLM returns empty string."""
    mock_response = MagicMock()
    mock_response.content = ""

    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=mock_response)

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        with pytest.raises(RuntimeError, match="unexpectedly short"):
            await story_to_resume("Some narrative text here.", mock_client)


@pytest.mark.asyncio
async def test_story_to_resume_raises_on_short_output():
    """story_to_resume raises RuntimeError when LLM output < 100 chars."""
    mock_response = MagicMock()
    mock_response.content = "Too short."

    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=mock_response)

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        with pytest.raises(RuntimeError, match="unexpectedly short"):
            await story_to_resume("Some narrative text here.", mock_client)


@pytest.mark.asyncio
async def test_story_to_resume_retries_unfilled_template():
    """Echoed format placeholders trigger one retry, then the filled draft is used."""
    template = MagicMock()
    template.content = EMPTY_TEMPLATE
    filled = MagicMock()
    filled.content = MOCK_DRAFT

    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(side_effect=[template, filled])

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        result = await story_to_resume("I worked at SecureAuth for three years.", mock_client)

    assert result.strip() == MOCK_DRAFT.strip()
    assert mock_client.complete.call_count == 2


@pytest.mark.asyncio
async def test_story_to_resume_raises_if_template_persists():
    """Two unfilled templates in a row fail instead of saving a blank resume."""
    template = MagicMock()
    template.content = EMPTY_TEMPLATE
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=template)

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        with pytest.raises(RuntimeError, match="empty template"):
            await story_to_resume("I worked at SecureAuth for three years.", mock_client)


def test_unfilled_template_detection():
    assert _is_unfilled_template(EMPTY_TEMPLATE) is True
    assert _is_unfilled_template(MOCK_DRAFT) is False


def test_story_prompt_file_exists_and_has_placeholder():
    """story_to_resume.txt must exist and contain the {narrative} placeholder."""
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent.parent / "app" / "agent" / "prompts" / "story_to_resume.txt"
    assert prompt_path.exists(), "story_to_resume.txt must exist"
    content = prompt_path.read_text()
    assert "{narrative}" in content, "Prompt must contain {narrative} placeholder"
    assert content.count("{narrative}") == 1, "Prompt must contain {narrative} exactly once"
    assert "[Company Name]" not in content
    assert "[text]" not in content
