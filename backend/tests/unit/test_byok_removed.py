"""Regression tests: BYOK removed — platform LLM only."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from app.models.session import Session
from app.models.user import User
from app.routers.auth import OnboardingPatchRequest
from app.services.llm_session_config import apply_llm_request_headers


def test_user_model_has_no_byok_columns() -> None:
    mapper = inspect(User)
    col_names = {attr.key for attr in mapper.column_attrs}
    assert "byok_api_key" not in col_names
    assert "byok_provider" not in col_names
    assert "byok_key_fingerprint" not in col_names


def test_session_model_has_no_byok_api_key_field() -> None:
    assert "byok_api_key" not in Session.model_fields


def test_onboarding_patch_rejects_byok_choice() -> None:
    with pytest.raises(ValidationError):
        OnboardingPatchRequest(ai_choice="byok")  # type: ignore[arg-type]


def test_apply_llm_request_headers_only_sets_provider_model() -> None:
    session = Session(session_id=str(uuid.uuid4()))
    apply_llm_request_headers(
        session,
        x_provider="gemini",
        x_model="gemini-2.5-flash",
    )
    assert session.provider == "gemini"
    assert session.model == "gemini-2.5-flash"
