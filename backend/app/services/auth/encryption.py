"""AES-256-GCM helpers used for BYOK API keys and TOTP secrets at rest.

Format
------

``encrypt_bytes(plaintext) -> nonce(12) || ciphertext_with_tag(N+16)``

The 12-byte nonce is generated per call with ``os.urandom`` (NIST-recommended
for GCM) and prepended to the ciphertext so ``decrypt_bytes`` can reconstruct
it without any sidecar state.

The encryption key is derived from ``BYOK_ENCRYPTION_KEY`` (a 32-byte hex
string).  Hex was chosen because all canonical secret rotators (`secrets`,
`openssl rand -hex 32`, etc.) emit it natively, and because hex round-trips
through env vars without quoting hazards that base64 introduces.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import is_production_grade, settings

# Length constants
_KEY_LEN_BYTES = 32   # AES-256
_NONCE_LEN_BYTES = 12  # GCM standard


class EncryptionConfigError(RuntimeError):
    """``BYOK_ENCRYPTION_KEY`` is missing or malformed."""


@lru_cache(maxsize=1)
def _load_key() -> bytes:
    """Decode ``BYOK_ENCRYPTION_KEY`` once and cache the raw bytes.

    In production-grade environments an unset/short key aborts the call;
    in local dev we tolerate any non-empty hex of correct length but still
    refuse outright-empty input — silent fallback to a deterministic key
    would be a footgun.
    """
    raw = settings.BYOK_ENCRYPTION_KEY.strip()
    if not raw:
        if is_production_grade():
            raise EncryptionConfigError(
                "BYOK_ENCRYPTION_KEY is required in production-grade environments."
            )
        raise EncryptionConfigError(
            "BYOK_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c 'import secrets; print(secrets.token_hex(32))'`."
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:  # pragma: no cover - very simple branch
        raise EncryptionConfigError(
            "BYOK_ENCRYPTION_KEY must be a hex string."
        ) from exc
    if len(key) != _KEY_LEN_BYTES:
        raise EncryptionConfigError(
            f"BYOK_ENCRYPTION_KEY must decode to {_KEY_LEN_BYTES} bytes, "
            f"got {len(key)}."
        )
    return key


def _cipher() -> AESGCM:
    return AESGCM(_load_key())


def encrypt_bytes(data: bytes, *, associated_data: bytes | None = None) -> bytes:
    """Return ``nonce || ciphertext_with_tag``.

    ``associated_data`` may be passed for authenticated additional data
    (e.g. ``b"byok:" + user_id``) so a ciphertext for one record cannot
    be swapped onto another.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("encrypt_bytes requires bytes")
    nonce = os.urandom(_NONCE_LEN_BYTES)
    ct = _cipher().encrypt(nonce, bytes(data), associated_data)
    return nonce + ct


def decrypt_bytes(blob: bytes, *, associated_data: bytes | None = None) -> bytes:
    """Inverse of :func:`encrypt_bytes`.

    Raises
    ------
    ValueError
        If the blob is too short to contain a nonce.
    cryptography.exceptions.InvalidTag
        If the ciphertext was tampered with or the key is wrong.
    """
    if not isinstance(blob, (bytes, bytearray)):
        raise TypeError("decrypt_bytes requires bytes")
    if len(blob) < _NONCE_LEN_BYTES + 16:
        raise ValueError("ciphertext too short — missing nonce or tag")
    nonce = bytes(blob[:_NONCE_LEN_BYTES])
    ct = bytes(blob[_NONCE_LEN_BYTES:])
    return _cipher().decrypt(nonce, ct, associated_data)


def reset_key_cache() -> None:
    """Test-only helper: clear the cached key so the next call re-reads settings."""
    _load_key.cache_clear()


__all__ = [
    "EncryptionConfigError",
    "decrypt_bytes",
    "encrypt_bytes",
    "reset_key_cache",
]
