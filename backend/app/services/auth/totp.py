"""TOTP enrollment + verification + recovery codes.

Storage contract (SYSTEM_DESIGN_PHASE_2 §18.2):

- ``User.totp_secret`` holds the AES-256-GCM ciphertext of the base32
  TOTP secret (encrypted via ``services.auth.encryption``).
- ``User.totp_recovery_codes`` is a list of bcrypt hashes.  Plaintext
  codes are shown to the user **once** at enrollment confirmation.

We deliberately split enroll vs confirm: a fresh secret is generated and
encrypted onto the user during ``begin_enrollment``, but ``has_totp``
stays ``False`` until ``confirm_enrollment`` accepts a valid 6-digit
code.  This prevents an attacker who acquires the QR mid-flow from
locking the legitimate user out — the user can simply re-enroll until
they confirm.
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from typing import Iterable

import pyotp

from app.brand import PRODUCT_NAME
from app.services.auth.encryption import decrypt_bytes, encrypt_bytes
from app.services.auth.password import _pwd_context  # reuse bcrypt context

ISSUER = PRODUCT_NAME
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10  # alphanumeric chars (excluding ambiguous ones)
TOTP_WINDOW = 1  # accept ±1 step (≈ ±30 s)

_RECOVERY_ALPHABET = "".join(
    c for c in (string.ascii_uppercase + string.digits) if c not in "O01ILS"
)


@dataclass(frozen=True, slots=True)
class TotpEnrollment:
    """Returned to the client when starting enrollment."""

    secret_b32: str
    provisioning_uri: str
    encrypted_secret: bytes


def begin_enrollment(*, account_label: str) -> TotpEnrollment:
    """Generate a new TOTP secret + provisioning URI.

    Caller persists ``encrypted_secret`` onto ``User.totp_secret`` and
    surfaces ``provisioning_uri`` to the frontend (which renders the QR).
    """
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=account_label,
        issuer_name=ISSUER,
    )
    encrypted = encrypt_bytes(secret.encode("utf-8"))
    return TotpEnrollment(
        secret_b32=secret,
        provisioning_uri=uri,
        encrypted_secret=encrypted,
    )


def verify_totp_code(encrypted_secret: bytes, code: str) -> bool:
    """Verify a 6-digit code against the user's stored encrypted secret.

    Returns ``False`` for any malformed input — never raises so callers
    get a single boolean to gate.
    """
    if not encrypted_secret or not code:
        return False
    code = code.strip()
    if not (code.isdigit() and len(code) == 6):
        return False
    try:
        secret = decrypt_bytes(encrypted_secret).decode("utf-8")
    except Exception:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=TOTP_WINDOW)


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Return plaintext recovery codes (caller shows them once)."""
    return [_one_recovery_code() for _ in range(count)]


def _one_recovery_code() -> str:
    pick = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
    # Insert a dash for readability (XXXXX-XXXXX).
    return f"{pick[:5]}-{pick[5:]}"


def hash_recovery_codes(codes: Iterable[str]) -> list[str]:
    """Bcrypt-hash each plaintext code for storage on the user row."""
    return [_pwd_context.hash(c.strip().upper().replace("-", "")) for c in codes]


def consume_recovery_code(
    stored_hashes: list[str],
    *,
    code: str,
) -> tuple[bool, list[str]]:
    """Try to match ``code`` against any stored hash.

    Returns ``(matched, remaining_hashes)``.  Recovery codes are
    single-use — the matched hash is removed from the returned list so
    the caller can persist the slimmer set.
    """
    if not code or not stored_hashes:
        return False, list(stored_hashes)
    norm = code.strip().upper().replace("-", "")
    remaining: list[str] = []
    matched = False
    for h in stored_hashes:
        if not matched and _pwd_context.verify(norm, h):
            matched = True
            continue  # skip — this is the consumed one
        remaining.append(h)
    return matched, remaining


__all__ = [
    "RECOVERY_CODE_COUNT",
    "TotpEnrollment",
    "begin_enrollment",
    "consume_recovery_code",
    "generate_recovery_codes",
    "hash_recovery_codes",
    "verify_totp_code",
]
