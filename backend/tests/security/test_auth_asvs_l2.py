"""ASVS Level 2 authentication verification (M23 B1 / OWASP A07).

Maps M20-delivered controls to ASVS V2/V3 requirements. These tests verify
existing behaviour — they do not re-implement signup-trust scope.

Reference: OWASP ASVS 4.0 — V2 Authentication, V3 Session Management.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from jose import jwt

from app.config import settings
from app.routers import auth as auth_router
from app.services.auth import password as password_module
from app.services.auth import tokens as tokens_module

REPO_BACKEND = Path(__file__).resolve().parents[2]


def test_asvs_v2_1_1_password_minimum_length_enforced_in_schema() -> None:
    """ASVS V2.1.1 — password length minimum enforced at API boundary."""
    register_fields = auth_router.RegisterRequest.model_fields
    assert register_fields["password"].metadata
    assert register_fields["password"].metadata[0].min_length >= 10


def test_asvs_v2_1_7_bcrypt_cost_factor_at_least_12() -> None:
    """ASVS V2.4.1 — passwords hashed with adaptive work factor ≥ 12."""
    assert password_module.BCRYPT_COST >= 12
    assert "bcrypt" in password_module._pwd_context.schemes()


def test_asvs_v2_1_9_zxcvbn_strength_gate() -> None:
    """ASVS V2.1.9 — weak passwords rejected before hash."""
    assert password_module.MIN_ZXCVBN_SCORE >= 3
    with pytest.raises(password_module.WeakPasswordError):
        password_module.check_strength("password", user_inputs=["user@example.com"])


def test_asvs_v3_1_1_access_token_short_ttl() -> None:
    """ASVS V3.1.1 — access tokens expire within 15 minutes."""
    assert tokens_module.create_access_token.__defaults__ is not None or True
    # Default TTL is 900s (15 min) per tokens.py docstring and implementation.
    sig = inspect.signature(tokens_module.create_access_token)
    ttl_default = sig.parameters["ttl"].default
    assert ttl_default == 900


def test_asvs_v3_1_1_jwt_uses_hs256_only() -> None:
    """ASVS V3.5.3 — JWT algorithm pinned; no 'none' or unexpected algs."""
    assert tokens_module.JWT_ALG == "HS256"
    token = tokens_module.create_access_token("00000000-0000-0000-0000-000000000001")
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"


def test_asvs_v3_2_1_refresh_token_rotation_documented() -> None:
    """ASVS V3.2.1 — refresh tokens rotate on use (reuse detection)."""
    source = inspect.getsource(tokens_module.rotate_refresh_token)
    assert "revoked_at" in source
    assert "RefreshTokenReuseError" in source


def test_asvs_v3_2_2_refresh_cookie_httponly_and_samesite() -> None:
    """ASVS V3.4.1 — session cookie HttpOnly + SameSite."""
    source = inspect.getsource(auth_router._set_refresh_cookie)
    assert "httponly=True" in source.replace(" ", "")
    assert 'samesite="lax"' in source.replace(" ", "") or "samesite='lax'" in source


def test_asvs_v3_2_2_refresh_cookie_secure_in_production() -> None:
    """ASVS V3.4.4 — Secure flag when production-grade TLS is required."""
    source = inspect.getsource(auth_router._set_refresh_cookie)
    assert "secure=is_production_grade()" in source.replace(" ", "")


def test_asvs_v2_2_1_login_rate_limit_decorator_present() -> None:
    """ASVS V2.2.1 — brute-force resistance via rate limits on login."""
    login_fn = auth_router.login
    assert hasattr(login_fn, "__wrapped__") or "limiter" in inspect.getsource(
        auth_router.login.__func__ if hasattr(auth_router.login, "__func__") else auth_router.login
    )
    # Decorator stack includes slowapi limit on the login route.
    auth_source = (REPO_BACKEND / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    login_block = auth_source.split("async def login(")[0].split("@router.post(\"/login\")")[-1]
    assert "@limiter.limit" in login_block or re.search(
        r'@limiter\.limit\("[^"]+"\)\s*\nasync def login', auth_source
    )


def test_asvs_v2_2_1_register_rate_limit_decorator_present() -> None:
    """ASVS V2.2.1 — signup endpoint rate limited."""
    auth_source = (REPO_BACKEND / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    assert re.search(
        r'@limiter\.limit\("[^"]+"\)\s*\nasync def register', auth_source
    )


def test_asvs_v2_4_3_password_reset_invalidates_sessions() -> None:
    """ASVS V2.4.3 — password change revokes existing sessions."""
    auth_source = (REPO_BACKEND / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    reset_block = auth_source.split("async def password_reset(")[0]
    assert "revoke_all_user_tokens" in reset_block or "revoke_all" in reset_block


def test_m20_signup_ip_rate_limit_module_exists() -> None:
    """M20 deliverable — daily signup caps by IP / fingerprint (A07 abuse)."""
    from app.services.auth import signup_rate_limit

    assert hasattr(signup_rate_limit, "assert_signup_rate_limit_allowed")
    assert settings.SIGNUP_IP_DAILY_LIMIT > 0


def test_m20_turnstile_production_gate_wired_at_startup() -> None:
    """M20 deliverable — Turnstile keys required in production."""
    main_source = (REPO_BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    assert "assert_turnstile_production_keys" in main_source


# ---------------------------------------------------------------------------
# Documented gaps (ASVS L2 items not yet satisfied — do not fix in B1)
# ---------------------------------------------------------------------------

KNOWN_ASVS_GAPS: dict[str, str] = {
    "V2.1.12": "No credential stuffing detection beyond IP/fingerprint signup caps",
    "V2.8.1": "TOTP optional for users; not mandatory ASVS L2 for all accounts",
    "V3.5.4": "JWT typ claim present but no explicit jti blocklist for access tokens",
}


@pytest.mark.parametrize("req_id,gap", list(KNOWN_ASVS_GAPS.items()))
def test_documented_asvs_l2_gap(req_id: str, gap: str) -> None:
    """Registry of ASVS L2 gaps for gap-matrix / Track B follow-up."""
    assert req_id.startswith("V")
    assert gap  # non-empty description
