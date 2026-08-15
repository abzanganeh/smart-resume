"""Unit tests for admin feature_unlock lookup and validation."""

from __future__ import annotations

import pytest

from app.models.admin_grant import AdminGrantType
from app.services.admin.feature_unlocks import (
    is_supported_feature_unlock,
    normalize_feature_name,
)
from app.services.admin.grants import InvalidGrantPayloadError, validate_grant_payload


def test_normalize_feature_name_lowercases_and_trims() -> None:
    assert normalize_feature_name("  Career_Watch  ") == "career_watch"


@pytest.mark.parametrize(
    "feature",
    ["whisper", "career_watch", "job_search", "fit_analysis"],
)
def test_validate_accepts_supported_feature_unlock(feature: str) -> None:
    validate_grant_payload(
        AdminGrantType.feature_unlock,
        {"feature": feature},
    )


def test_validate_rejects_unsupported_feature_unlock() -> None:
    with pytest.raises(InvalidGrantPayloadError, match="unsupported feature_unlock"):
        validate_grant_payload(
            AdminGrantType.feature_unlock,
            {"feature": "premium_llm"},
        )


def test_is_supported_feature_unlock_case_insensitive() -> None:
    assert is_supported_feature_unlock("Whisper") is True
    assert is_supported_feature_unlock("unknown") is False
