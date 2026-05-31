"""Password hashing and strength gating.

- ``hash_password`` / ``verify_password``: bcrypt cost factor 12 (§18.2).
- ``check_strength``: rejects any password with zxcvbn score < 3 (§18.2).

bcrypt's plaintext is silently truncated past 72 bytes, so we explicitly
reject anything longer than 72 bytes here.  Callers normalise to UTF-8
NFC before hashing.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from passlib.context import CryptContext
from zxcvbn import zxcvbn

from app.services.auth.exceptions import WeakPasswordError

BCRYPT_COST = 12
MIN_PASSWORD_CHARS = 10
MIN_ZXCVBN_SCORE = 3
MAX_PASSWORD_BYTES = 72  # bcrypt hard limit


_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=BCRYPT_COST,
)


def _normalise(plain: str) -> str:
    """Apply Unicode NFC so visually-equivalent inputs hash identically."""
    return unicodedata.normalize("NFC", plain)


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt cost 12.

    Raises ``ValueError`` if the UTF-8 byte length exceeds bcrypt's 72-byte
    cap; this avoids the silent truncation issue.
    """
    if not isinstance(plain, str):
        raise TypeError("hash_password requires str")
    normal = _normalise(plain)
    if len(normal.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            "Password exceeds bcrypt's 72-byte limit. "
            "Use a passphrase-friendly KDF (e.g. argon2) for longer inputs."
        )
    return _pwd_context.hash(normal)


def verify_password(plain: str, hashed: str | None) -> bool:
    """Constant-time comparison of ``plain`` against ``hashed``.

    Returns ``False`` (not raise) when ``hashed`` is ``None`` — SSO-only
    accounts with no password should still hit a uniform negative result
    so the response time looks identical to a wrong-password attempt.
    """
    if not hashed:
        # Run a dummy verify against a known hash so timing stays comparable
        # for a real "wrong password" attempt.
        _pwd_context.dummy_verify()
        return False
    try:
        return _pwd_context.verify(_normalise(plain), hashed)
    except (ValueError, TypeError):
        return False


def get_bcrypt_cost(hashed: str) -> int:
    """Parse the bcrypt cost factor from an encoded hash for assertions."""
    # bcrypt encoding: $2b$<cost>$<22-char-salt><31-char-hash>
    parts = hashed.split("$")
    if len(parts) < 4 or parts[1] not in {"2a", "2b", "2y"}:
        raise ValueError("not a bcrypt hash")
    return int(parts[2])


def check_strength(plain: str, *, user_inputs: list[str] | None = None) -> dict[str, Any]:
    """Validate password strength.

    Raises :class:`WeakPasswordError` if length < 10 or zxcvbn score < 3.
    Returns the full zxcvbn report on success for callers that want to
    display feedback.

    ``user_inputs`` lets the caller pass user-known strings (email,
    display name) so zxcvbn penalises inclusion of those values.
    """
    if not isinstance(plain, str):
        raise TypeError("check_strength requires str")
    normal = _normalise(plain)
    if len(normal) < MIN_PASSWORD_CHARS:
        raise WeakPasswordError(
            score=0,
            suggestions=[f"Use at least {MIN_PASSWORD_CHARS} characters."],
        )
    report = zxcvbn(normal, user_inputs=user_inputs or [])
    score = int(report.get("score", 0))
    if score < MIN_ZXCVBN_SCORE:
        feedback = report.get("feedback") or {}
        suggestions = list(feedback.get("suggestions") or [])
        warning = feedback.get("warning")
        if warning:
            suggestions.insert(0, warning)
        raise WeakPasswordError(score=score, suggestions=suggestions)
    return report


__all__ = [
    "BCRYPT_COST",
    "MAX_PASSWORD_BYTES",
    "MIN_PASSWORD_CHARS",
    "MIN_ZXCVBN_SCORE",
    "check_strength",
    "get_bcrypt_cost",
    "hash_password",
    "verify_password",
]
