"""Privacy and security disclosure checks (M23 B4 / OWASP A02, GDPR).

Static assertions on published legal copy and SECURITY.md — no runtime PII.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRIVACY_PAGE = REPO_ROOT / "frontend" / "app" / "legal" / "privacy" / "page.tsx"
SECURITY_MD = REPO_ROOT / "SECURITY.md"
CLOSURE_SOURCE = (
    REPO_ROOT / "backend" / "app" / "services" / "export" / "closure.py"
)


def test_privacy_policy_discloses_signup_ip_and_fingerprint() -> None:
    text = PRIVACY_PAGE.read_text(encoding="utf-8")
    assert "signup IP" in text.lower() or "Signup IP" in text
    assert "fingerprint" in text.lower()
    assert "legitimate interest" in text.lower()


def test_privacy_policy_discloses_embedding_erasure_on_closure() -> None:
    text = PRIVACY_PAGE.read_text(encoding="utf-8")
    assert "embedding" in text.lower()
    assert "closure" in text.lower() or "erasure" in text.lower()
    assert "hard-delet" in text.lower() or "purged" in text.lower()


def test_closure_service_hard_deletes_user_row() -> None:
    """Implementation backing GDPR Art. 17 erasure claims."""
    source = CLOSURE_SOURCE.read_text(encoding="utf-8")
    assert "execute_closure" in source
    assert "delete(User)" in source.replace(" ", "")


def test_security_md_pgp_not_a_bare_tbd() -> None:
    text = SECURITY_MD.read_text(encoding="utf-8")
    assert "PGP" in text
    assert "TBD" not in text.split("PGP")[1].split("\n")[0]


def test_security_md_documents_crypto_controls() -> None:
    text = SECURITY_MD.read_text(encoding="utf-8")
    assert "Cryptography" in text or "BYOK" in text
    assert "AES-256-GCM" in text or "AES-256" in text
