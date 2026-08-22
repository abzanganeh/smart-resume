"""Crypto configuration gates exercised in production-grade environments (A04 baseline)."""

from __future__ import annotations

import pytest

from app.config import settings
from app.services.auth.encryption import EncryptionConfigError, reset_key_cache


@pytest.mark.parametrize("app_env", ["ci", "staging", "production"])
def test_byok_key_required_in_production_grade_envs(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
) -> None:
    reset_key_cache()
    monkeypatch.setattr(settings, "APP_ENV", app_env)
    monkeypatch.setattr(settings, "BYOK_ENCRYPTION_KEY", "")

    with pytest.raises(EncryptionConfigError, match="required in production-grade"):
        from app.services.auth import encryption

        encryption._load_key()


def test_byok_key_rejects_malformed_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_key_cache()
    monkeypatch.setattr(settings, "APP_ENV", "ci")
    monkeypatch.setattr(settings, "BYOK_ENCRYPTION_KEY", "not-hex")

    with pytest.raises(EncryptionConfigError, match="hex string"):
        from app.services.auth import encryption

        encryption._load_key()
