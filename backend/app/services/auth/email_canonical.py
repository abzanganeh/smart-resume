"""Provider-aware email canonicalization for signup uniqueness."""

from __future__ import annotations

_GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})

_PLUS_SUFFIX_ALLOWLIST = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "fastmail.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
    }
)


def _split_email(email: str) -> tuple[str, str]:
    local, _, domain = email.partition("@")
    if not local or not domain:
        return email, ""
    return local, domain.lower()


def _strip_plus_suffix(local: str) -> str:
    base, _, _suffix = local.partition("+")
    return base


def canonicalize_email(email: str) -> str:
    """Return the canonical identity key for ``email``.

    Gmail/googlemail: strip dots and ``+suffix`` from the local part.
    Allowlisted providers: strip ``+suffix`` only.
    Unknown/corporate domains: lowercase only — no alias normalization.
    """
    normalized = email.strip().lower()
    local, domain = _split_email(normalized)
    if not domain:
        return normalized

    if domain in _GMAIL_DOMAINS:
        local = _strip_plus_suffix(local).replace(".", "")
    elif domain in _PLUS_SUFFIX_ALLOWLIST:
        local = _strip_plus_suffix(local)

    return f"{local}@{domain}"


__all__ = ["canonicalize_email"]
