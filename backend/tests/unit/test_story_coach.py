"""Unit tests for agent/story_coach.py."""
from __future__ import annotations

import pytest

from app.agent.story_coach import MAX_EXCHANGES, _build_history_text, is_complete_response


class TestBuildHistoryText:
    def test_empty_history(self):
        result = _build_history_text([])
        assert result == "(no prior exchanges)"

    def test_single_coach_message(self):
        result = _build_history_text([{"role": "coach", "text": "How many engineers?"}])
        assert "Coach: How many engineers?" in result

    def test_multi_turn(self):
        history = [
            {"role": "coach", "text": "How many?"},
            {"role": "user", "text": "Six."},
            {"role": "coach", "text": "What was the timeline?"},
        ]
        result = _build_history_text(history)
        assert "Coach: How many?" in result
        assert "User: Six." in result
        assert "Coach: What was the timeline?" in result


class TestIsCompleteResponse:
    def test_complete_prefix_detected(self):
        assert is_complete_response("COMPLETE: This segment is already strong.") is True

    def test_complete_with_leading_whitespace(self):
        assert is_complete_response("  COMPLETE: fine") is True

    def test_regular_question_not_complete(self):
        assert is_complete_response("How many engineers were on the team?") is False

    def test_empty_string(self):
        assert is_complete_response("") is False


class TestMaxExchanges:
    def test_max_exchanges_is_three(self):
        assert MAX_EXCHANGES == 3


class TestCoachSegmentStreaming:
    @pytest.mark.asyncio
    async def test_streams_non_empty_response(self):
        """coach_segment should yield at least one non-empty delta."""

        class FakeLLMClient:
            async def stream(self, messages, max_tokens=80):
                yield "How"
                yield " many engineers were on your team?"

        from app.agent.story_coach import coach_segment

        history: list = []
        deltas = []
        async for delta in coach_segment(
            segment_text="I led the migration to Kubernetes.",
            history=history,
            llm_client=FakeLLMClient(),
        ):
            deltas.append(delta)

        assert len(deltas) > 0
        full = "".join(deltas)
        assert len(full) > 5

    @pytest.mark.asyncio
    async def test_streams_complete_sentinel(self):
        """coach_segment passes through COMPLETE: responses without error."""

        class FakeLLMClient:
            async def stream(self, messages, max_tokens=80):
                yield "COMPLETE: This segment is already strong."

        from app.agent.story_coach import coach_segment, is_complete_response

        history = [
            {"role": "coach", "text": "How many?"},
            {"role": "user", "text": "Six engineers, 3-month timeline, 40% latency reduction."},
        ]
        result = ""
        async for delta in coach_segment(
            segment_text="Led 6-engineer team, 3-month K8s migration, cut latency 40%.",
            history=history,
            llm_client=FakeLLMClient(),
        ):
            result += delta

        assert is_complete_response(result)
