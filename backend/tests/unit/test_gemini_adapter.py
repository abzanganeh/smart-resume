"""Unit tests for Gemini 3.x adapter helpers."""
from types import SimpleNamespace

from app.llm.providers.gemini_adapter import GeminiAdapter


def test_gemini_3_expands_output_token_cap():
    adapter = GeminiAdapter(model="gemini-3.6-flash", api_key="test-key")
    assert adapter._output_token_cap(1500) == 4096


def test_gemini_25_keeps_requested_cap():
    adapter = GeminiAdapter(model="gemini-2.5-flash", api_key="test-key")
    assert adapter._output_token_cap(1500) == 1500


def test_visible_text_skips_thought_parts():
    adapter = GeminiAdapter(model="gemini-3.6-flash", api_key="test-key")
    resp = SimpleNamespace(
        text="",
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(thought=True, text="hidden reasoning"),
                        SimpleNamespace(thought=False, text="PROFESSIONAL SUMMARY\nEngineer"),
                    ]
                )
            )
        ],
    )
    assert adapter._visible_text(resp) == "PROFESSIONAL SUMMARY\nEngineer"
