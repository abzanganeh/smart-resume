"""Apply LLM provider / model headers from incoming requests to a session."""

from __future__ import annotations

from app.models.session import Session


def apply_llm_request_headers(
    session: Session,
    *,
    x_provider: str | None,
    x_model: str | None,
) -> None:
    """Sync session LLM config from request headers before an LLM-backed action."""
    if x_provider:
        session.provider = x_provider
    if x_model:
        session.model = x_model
