"""Vendored disposable-email domain blocklist for signup."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_BLOCKLIST_FILENAME = "disposable_email_domains.txt"
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _blocklist_path() -> Path:
    return _DATA_DIR / _BLOCKLIST_FILENAME


def load_disposable_domains(*, path: Path | None = None) -> frozenset[str]:
    """Load the vendored domain blocklist from disk."""
    target = path or _blocklist_path()
    if not target.is_file():
        raise FileNotFoundError(f"disposable domain blocklist missing: {target}")
    domains: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        domain = line.strip().lower()
        if domain and not domain.startswith("#"):
            domains.add(domain)
    return frozenset(domains)


@lru_cache(maxsize=1)
def disposable_domains() -> frozenset[str]:
    return load_disposable_domains()


def _domain_suffixes(domain: str) -> tuple[str, ...]:
    parts = domain.split(".")
    if len(parts) < 2:
        return (domain,)
    return tuple(".".join(parts[i:]) for i in range(len(parts) - 1))


def is_disposable_email(email: str) -> bool:
    """Return True when ``email`` uses a known disposable provider domain."""
    _, _, domain = email.strip().lower().partition("@")
    if not domain:
        return False
    blocklist = disposable_domains()
    return any(suffix in blocklist for suffix in _domain_suffixes(domain))


def reload_disposable_domains(*, path: Path | None = None) -> frozenset[str]:
    """Test helper — reload the cached blocklist from disk."""
    disposable_domains.cache_clear()
    if path is not None:
        return load_disposable_domains(path=path)
    return disposable_domains()


__all__ = [
    "disposable_domains",
    "is_disposable_email",
    "load_disposable_domains",
    "reload_disposable_domains",
]
