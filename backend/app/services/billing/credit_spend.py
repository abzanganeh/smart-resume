"""Shared helpers for free-credit spend eligibility."""

from __future__ import annotations

from app.models.user import User


def spendable_free_credits(user: User, *, balance: int) -> int:
    """Return the portion of ``balance`` the user may spend right now."""
    if not user.is_email_verified:
        return 0
    return max(0, balance)


def credits_locked_until_verification(user: User, *, balance: int) -> bool:
    return balance > 0 and not user.is_email_verified


def credits_locked_detail(*, balance: int) -> dict[str, int | str]:
    return {
        "code": "credits_locked_until_verification",
        "balance": balance,
        "message": "Verify your email to use your free credits.",
    }


__all__ = [
    "credits_locked_detail",
    "credits_locked_until_verification",
    "spendable_free_credits",
]
