"""Model choice must never come from the caller (M18 slice 3 closeout).

Platform API keys pay for every non-BYOK call, so a route that resolves its
provider/model from request headers, a request body, or a stored session field
lets a caller pick the most expensive model in the price table and bill it to
the platform. Model choice belongs to the step registry alone.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.llm.model_registry import STEP_DEFAULTS, resolve_model
from app.llm.pricing import has_price_row
from app.routers.resume import paste_resume, suggest_audit_bullet_fixes, upload_resume
from app.routers.sessions import chat_with_resume


pytestmark = pytest.mark.unit


_ROUTERS_DIR = Path(__file__).resolve().parents[2] / "app" / "routers"

# `llm.py` owns `POST /api/llm/verify`, whose whole purpose is to prove a
# caller-supplied provider/model pair works. It is authenticated, rate limited
# to 5/minute and capped at 5 output tokens, so the caller-chosen model cannot
# amplify spend. Every other router must go through the step registry.
_CALLER_CHOSEN_MODEL_ALLOWLIST = {"llm.py"}

_HANDLERS_WITHOUT_MODEL_INPUT = (
    upload_resume,
    paste_resume,
    suggest_audit_bullet_fixes,
    chat_with_resume,
)


def _router_sources() -> list[tuple[str, str]]:
    return [
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(_ROUTERS_DIR.glob("*.py"))
    ]


def test_routers_resolve_models_through_the_step_registry() -> None:
    """`get_llm_client(...)` bypasses the registry; routers must not call it."""
    offenders = [
        name
        for name, source in _router_sources()
        if name not in _CALLER_CHOSEN_MODEL_ALLOWLIST and "get_llm_client(" in source
    ]
    assert not offenders, (
        "These routers bypass the step registry: "
        + ", ".join(offenders)
        + ". Use get_llm_client_for_step(<step>) instead."
    )


def test_no_router_routes_on_stored_session_provider_or_model() -> None:
    session_provider_pattern = re.compile(r"\bsession\.provider\b")
    session_model_pattern = re.compile(r"\bsession\.model\b")
    offenders = [
        name
        for name, source in _router_sources()
        if session_provider_pattern.search(source) or session_model_pattern.search(source)
    ]
    assert not offenders, (
        "These routers still read a session-stored provider/model: "
        + ", ".join(offenders)
    )


@pytest.mark.parametrize("handler", _HANDLERS_WITHOUT_MODEL_INPUT)
def test_llm_backed_handlers_accept_no_provider_or_model_argument(handler) -> None:
    params = set(inspect.signature(handler).parameters)
    assert not params & {"x_provider", "x_model", "provider", "model"}, (
        f"{handler.__name__} still accepts a caller-supplied model"
    )


def test_resume_structure_step_is_pinned_to_cheap_flash_lite() -> None:
    assert resolve_model("resume_structure") == ("gemini", "gemini-3.5-flash-lite")


def test_every_pinned_step_model_has_a_price_row() -> None:
    """A step that routes real traffic must also be priceable."""
    missing = [
        f"{step} -> {provider}/{model}"
        for step, (provider, model) in STEP_DEFAULTS.items()
        if not has_price_row(provider, model)
    ]
    assert not missing, "Steps pinned to unpriced models: " + "; ".join(missing)
