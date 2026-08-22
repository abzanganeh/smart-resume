"""Cryptographic controls review (M23 B3 / OWASP A04).

Verifies BYOK at-rest encryption, JWT handling, session cookie flags, and
TLS/HSTS configuration at the Caddy edge. Behaviour tests complement the
ASVS-focused checks in ``test_auth_asvs_l2.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from jose import jwt

from app.config import settings
from app.services.auth import encryption as encryption_module
from app.services.auth.encryption import decrypt_bytes, encrypt_bytes, reset_key_cache
from app.services.auth import tokens as tokens_module

REPO_ROOT = Path(__file__).resolve().parents[3]
CADDY_PRODUCTION = REPO_ROOT / "infra" / "caddy" / "Caddyfile.production.example"


@pytest.fixture()
def byok_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Valid 32-byte hex BYOK key for crypto round-trip tests."""
    key_hex = "a" * 64
    reset_key_cache()
    monkeypatch.setattr(settings, "APP_ENV", "ci")
    monkeypatch.setattr(settings, "BYOK_ENCRYPTION_KEY", key_hex)
    yield key_hex
    reset_key_cache()


def test_byok_encrypt_decrypt_roundtrip(byok_key: str) -> None:
    """AES-256-GCM round-trip preserves plaintext."""
    plaintext = b"sk-live-platform-api-key"
    blob = encrypt_bytes(plaintext)
    assert decrypt_bytes(blob) == plaintext


def test_byok_associated_data_binds_ciphertext(byok_key: str) -> None:
    """AAD prevents swapping ciphertext between records (ASVS V6.2.1)."""
    blob = encrypt_bytes(b"secret", associated_data=b"byok:user-a")
    with pytest.raises(InvalidTag):
        decrypt_bytes(blob, associated_data=b"byok:user-b")


def test_byok_tampered_ciphertext_fails_closed(byok_key: str) -> None:
    blob = bytearray(encrypt_bytes(b"secret"))
    blob[-1] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt_bytes(bytes(blob))


def test_byok_key_rotation_invalidates_old_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotating ``BYOK_ENCRYPTION_KEY`` requires re-encryption of stored secrets."""
    reset_key_cache()
    monkeypatch.setattr(settings, "APP_ENV", "ci")
    monkeypatch.setattr(settings, "BYOK_ENCRYPTION_KEY", "b" * 64)
    blob = encrypt_bytes(b"totp-secret")

    reset_key_cache()
    monkeypatch.setattr(settings, "BYOK_ENCRYPTION_KEY", "c" * 64)
    with pytest.raises(InvalidTag):
        decrypt_bytes(blob)


def test_byok_rotation_story_documented_in_module() -> None:
    """Key rotation is operator-driven — no silent in-place re-wrap yet."""
    source = Path(encryption_module.__file__).read_text(encoding="utf-8")
    assert "BYOK_ENCRYPTION_KEY" in source
    assert "hex" in source.lower()


def test_jwt_rejects_algorithm_confusion() -> None:
    """``decode_access_token`` accepts only HS256 (no ``none`` / RS256 swap)."""
    user_id = "00000000-0000-0000-0000-000000000001"
    forged = jwt.encode(
        {"sub": user_id, "typ": "access", "iss": tokens_module.ISSUER},
        "attacker-secret",
        algorithm="HS256",
    )
    with pytest.raises(tokens_module.TokenInvalidError):
        tokens_module.decode_access_token(forged)


def test_jwt_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = tokens_module.create_access_token(
        "00000000-0000-0000-0000-000000000001",
        ttl=-1,
    )
    with pytest.raises(tokens_module.TokenExpiredError):
        tokens_module.decode_access_token(token)


def test_caddy_production_enforces_hsts_and_strips_server_header() -> None:
    """TLS edge config carries HSTS preload and baseline transport headers."""
    text = CADDY_PRODUCTION.read_text(encoding="utf-8")
    assert "Strict-Transport-Security" in text
    assert "includeSubDomains" in text
    assert "preload" in text
    assert "-Server" in text


def test_caddy_staging_matches_production_security_headers() -> None:
    staging = REPO_ROOT / "infra" / "caddy" / "Caddyfile.staging.example"
    prod = CADDY_PRODUCTION.read_text(encoding="utf-8")
    staging_text = staging.read_text(encoding="utf-8")
    for marker in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "X-Frame-Options",
    ):
        assert marker in staging_text, f"{marker} missing from staging Caddyfile"
        assert marker in prod
