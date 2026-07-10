"""Unit tests for Flint credit scaffold helpers (no DB required)."""

from __future__ import annotations

import uuid

import pytest

from app.services.billing.flint_credits import (
    FLINT_ACTION_COSTS,
    create_hold,
    flint_action_cost,
    release_hold,
    reset_holds_for_tests,
)


def test_flint_action_cost_matches_strategy_b_defaults() -> None:
    assert flint_action_cost("rehearsal_turn") == 15
    assert flint_action_cost("live_turn") == 15
    assert flint_action_cost("pre_warm") == 50
    assert len(FLINT_ACTION_COSTS) >= 6


def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError, match="unknown Flint action"):
        flint_action_cost("not_a_real_action")


def test_hold_lifecycle_in_memory() -> None:
    reset_holds_for_tests()
    user_id = uuid.uuid4()
    hold_id = create_hold(user_id=user_id, session_id="sess-abc", amount=100)
    release_hold(hold_id=hold_id, user_id=user_id)
    with pytest.raises(KeyError):
        release_hold(hold_id=hold_id, user_id=user_id)


def test_hold_wrong_user_raises() -> None:
    reset_holds_for_tests()
    owner = uuid.uuid4()
    other = uuid.uuid4()
    hold_id = create_hold(user_id=owner, session_id="sess-x", amount=25)
    with pytest.raises(PermissionError):
        release_hold(hold_id=hold_id, user_id=other)
    release_hold(hold_id=hold_id, user_id=owner)
