"""Typed exceptions raised by the auth service layer.

The router layer translates these into HTTP responses; the service layer
never imports FastAPI HTTPException so it stays testable and reusable.
"""

from __future__ import annotations


class AuthError(Exception):
    """Base class for all auth-service errors."""


class InvalidCredentialsError(AuthError):
    """Email/password combo did not match."""


class AccountLockedError(AuthError):
    """Account is temporarily locked after too many failed logins."""


class AccountSuspendedError(AuthError):
    """Account has been suspended by an admin."""


class EmailAlreadyRegisteredError(AuthError):
    """Email already exists for a different provider or account."""


class EmailNotVerifiedError(AuthError):
    """Action requires a verified email."""


class WeakPasswordError(AuthError):
    """zxcvbn score < 3 — password rejected."""

    def __init__(self, score: int, suggestions: list[str] | None = None) -> None:
        super().__init__(f"Password too weak (zxcvbn score {score}/4)")
        self.score = score
        self.suggestions = suggestions or []


class TokenError(AuthError):
    """Base class for JWT / refresh-token errors."""


class TokenExpiredError(TokenError):
    pass


class TokenInvalidError(TokenError):
    pass


class RefreshTokenReuseError(TokenError):
    """A revoked refresh token was presented — the entire chain has been revoked."""

    def __init__(self, user_id: str | None = None) -> None:
        super().__init__("refresh token reuse detected")
        self.user_id = user_id


class TfaRequiredError(AuthError):
    """Login succeeded but TOTP step is required — return a 2fa_challenge token."""

    def __init__(self, challenge_token: str) -> None:
        super().__init__("2fa_required")
        self.challenge_token = challenge_token


class TfaInvalidError(AuthError):
    """TOTP / recovery code did not verify."""


class TfaAlreadyEnrolledError(AuthError):
    """User already has TOTP enrolled and confirmed."""


class TfaNotEnrolledError(AuthError):
    """User has no TOTP secret to verify against."""


class OAuthError(AuthError):
    """OAuth provider returned an error or unexpected payload."""


__all__ = [
    "AccountLockedError",
    "AccountSuspendedError",
    "AuthError",
    "EmailAlreadyRegisteredError",
    "EmailNotVerifiedError",
    "InvalidCredentialsError",
    "OAuthError",
    "RefreshTokenReuseError",
    "TfaAlreadyEnrolledError",
    "TfaInvalidError",
    "TfaNotEnrolledError",
    "TfaRequiredError",
    "TokenError",
    "TokenExpiredError",
    "TokenInvalidError",
    "WeakPasswordError",
]
