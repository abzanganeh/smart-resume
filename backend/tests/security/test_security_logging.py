"""Security logging invariants for OWASP A09 / LLM02 (M23 A3).

The redaction processor is exercised through a real structlog pipeline —
same processor order as ``app.main`` — rather than by calling it
directly, so the assertions cover what actually reaches stdout.

Fake credentials below are assembled from fragments at runtime so no
literal key-shaped string sits in the file for a secret scanner to flag.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest
import structlog

from app.services.security import logging as security_logging
from app.services.security.logging import (
    ACCESS_DENIED,
    ALERT_WORTHY_EVENTS,
    AUTH_LOGIN_FAILED,
    AUTH_SIGNUP_RATE_LIMITED,
    BILLING_WEBHOOK_NEEDS_REVIEW,
    BILLING_WEBHOOK_REJECTED,
    LLM_BUDGET_EXCEEDED,
    LLM_PROVIDER_ERROR,
    MAX_VALUE_CHARS,
    SECURITY_EVENTS,
    fingerprint,
    mask_ip,
    redact_sensitive,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

RESUME_MARKER = "XPII-RESUME-BODY"
RESUME_TEXT = (
    f"Alireza Candidate — Staff Engineer. {RESUME_MARKER}. "
    "Led the payments rewrite; cut p99 latency by 40%. " * 20
)
JD_MARKER = "XPII-JD-BODY"
CANDIDATE_EMAIL = "candidate.pii@example-pii.test"
OTHER_EMAIL = "someone.else@example-pii.test"
CLIENT_IPV4 = "203.0.113.42"
CLIENT_IPV6 = "2001:db8::dead:beef"
CANDIDATE_PHONE = "+1-555-0100"
CANDIDATE_NAME = "Alireza Zanganeh"

OPENAI_KEY = "sk-" + "proj-" + "PIIFIXTUREKEY" + "0" * 24
ANTHROPIC_KEY = "sk-" + "ant-" + "api03-" + "PIIFIXTUREKEY" + "0" * 24
GOOGLE_KEY = "AIza" + "PIIFIXTUREKEY" + "0" * 20
STRIPE_WEBHOOK_SECRET = "whsec_" + "PIIFIXTUREKEY" + "0" * 16
BEARER_TOKEN = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxIn0" + "." + "c2lnbmF0dXJl"

#: Every string that must never survive redaction at INFO or above.
PII_LITERALS = (
    RESUME_MARKER,
    JD_MARKER,
    CANDIDATE_EMAIL,
    OTHER_EMAIL,
    CLIENT_IPV4,
    CLIENT_IPV6,
    CANDIDATE_PHONE,
    CANDIDATE_NAME,
    OPENAI_KEY,
    ANTHROPIC_KEY,
    GOOGLE_KEY,
    STRIPE_WEBHOOK_SECRET,
    BEARER_TOKEN,
)


@pytest.fixture
def pii_fields() -> dict[str, Any]:
    """One record touching every PII channel the product handles.

    Mixes the well-known key names with free-text fields (``detail``,
    ``error``) where a call site accidentally interpolated PII into a
    message — the second case is what the value scanner exists for.
    """
    return {
        "user_id": "8f14e45f-ea24-4b1c-9f36-2b0e5c1f9a77",
        "resume_text": RESUME_TEXT,
        "job_description": f"Senior Engineer. {JD_MARKER}. Remote.",
        "email": CANDIDATE_EMAIL,
        "to_email": OTHER_EMAIL,
        "client_ip": CLIENT_IPV4,
        "remote_addr": CLIENT_IPV6,
        "phone": CANDIDATE_PHONE,
        "full_name": CANDIDATE_NAME,
        "api_key": OPENAI_KEY,
        "stripe_webhook_secret": STRIPE_WEBHOOK_SECRET,
        "detail": (
            f"provider rejected key {ANTHROPIC_KEY} for {CANDIDATE_EMAIL} "
            f"from {CLIENT_IPV4}"
        ),
        "error": f"401 Unauthorized (google key {GOOGLE_KEY}, jwt {BEARER_TOKEN})",
        "provider_response": {
            "headers": {"authorization": f"Bearer {BEARER_TOKEN}"},
            "candidates": [{"email": CANDIDATE_EMAIL, "resume": RESUME_TEXT}],
        },
    }


def emit(level: str, event: str, **fields: Any) -> str:
    """Log through the production processor chain, return the raw line.

    Deliberately does not touch the global ``structlog.configure`` state,
    so the pipeline under test cannot leak into other tests.
    """
    buffer = io.StringIO()
    logger = structlog.wrap_logger(
        structlog.PrintLogger(file=buffer),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    )
    getattr(logger, level)(event, **fields)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["info", "warning", "error", "critical"])
def test_pii_never_reaches_the_log_line(level: str, pii_fields: dict[str, Any]) -> None:
    line = emit(level, AUTH_LOGIN_FAILED, **pii_fields)

    for literal in PII_LITERALS:
        assert literal not in line, f"{literal!r} leaked into a {level} log line"


def test_debug_is_redacted_too(pii_fields: dict[str, Any]) -> None:
    """The contract is INFO+, but DEBUG is covered as defence in depth."""
    line = emit("debug", AUTH_LOGIN_FAILED, **pii_fields)

    for literal in PII_LITERALS:
        assert literal not in line


def test_event_name_and_correlation_ids_survive(pii_fields: dict[str, Any]) -> None:
    """Redaction must not defeat the point of the log line."""
    record = json.loads(emit("warning", ACCESS_DENIED, **pii_fields))

    assert record["event"] == ACCESS_DENIED
    assert record["level"] == "warning"
    assert record["user_id"] == pii_fields["user_id"]
    assert "timestamp" in record


def test_nested_containers_are_walked(pii_fields: dict[str, Any]) -> None:
    record = json.loads(emit("error", LLM_PROVIDER_ERROR, **pii_fields))
    nested = record["provider_response"]

    assert nested["headers"]["authorization"] == "<redacted:secret>"
    candidate = nested["candidates"][0]
    assert candidate["email"].startswith("<redacted:email:")
    assert candidate["resume"].startswith("<redacted:content:")


def test_email_fingerprint_correlates_without_exposing_the_address() -> None:
    first = json.loads(emit("info", AUTH_LOGIN_FAILED, email=CANDIDATE_EMAIL))
    again = json.loads(emit("info", AUTH_LOGIN_FAILED, email=CANDIDATE_EMAIL.upper()))
    other = json.loads(emit("info", AUTH_LOGIN_FAILED, email=OTHER_EMAIL))

    assert first["email"] == f"<redacted:email:{fingerprint(CANDIDATE_EMAIL)}>"
    assert again["email"] == first["email"], "fingerprint must ignore case"
    assert other["email"] != first["email"]


def test_client_ip_is_masked_to_its_network() -> None:
    record = json.loads(
        emit("info", AUTH_SIGNUP_RATE_LIMITED, client_ip=CLIENT_IPV4)
    )

    assert record["client_ip"] == "203.0.113.0/24"
    assert mask_ip(CLIENT_IPV6) == "2001:db8::/48"
    assert mask_ip("not-an-ip") == "<redacted:ip>"


def test_dotted_strings_that_are_not_addresses_pass_through() -> None:
    """Masking errs toward the address side of the ambiguity.

    A four-octet version string is indistinguishable from an IPv4
    literal, so it gets masked — an accepted false positive. Anything
    :mod:`ipaddress` rejects must survive untouched, otherwise ordinary
    diagnostics become unreadable.
    """
    record = json.loads(
        emit("info", LLM_PROVIDER_ERROR, detail="sdk 1.22.3 timed out after 2.5s")
    )
    assert record["detail"] == "sdk 1.22.3 timed out after 2.5s"

    masked = json.loads(emit("info", LLM_PROVIDER_ERROR, detail="sdk 1.22.3.4 failed"))
    assert masked["detail"] == "sdk 1.22.3.0/24 failed"


def test_oversized_values_under_unrecognised_keys_are_truncated() -> None:
    """The key-name lists are the primary defence; length is the backstop.

    A résumé logged under a key the module does not know about is still
    capped, so one log line cannot carry a whole document — but the head
    of it survives, which is why long-form content must be logged under a
    name in ``CONTENT_KEYS``.
    """
    record = json.loads(emit("info", ACCESS_DENIED, blob="x" * 5000))

    assert len(record["blob"]) < 5000
    assert record["blob"].endswith("<truncated 5000 chars>")
    assert record["blob"].startswith("x" * MAX_VALUE_CHARS)


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


def test_event_taxonomy_names_are_stable() -> None:
    """Alert rules key off these strings; renaming one is a breaking change."""
    assert AUTH_LOGIN_FAILED == "auth.login_failed"
    assert AUTH_SIGNUP_RATE_LIMITED == "auth.signup_rate_limited"
    assert BILLING_WEBHOOK_REJECTED == "billing.webhook_rejected"
    assert BILLING_WEBHOOK_NEEDS_REVIEW == "billing.webhook_needs_review"
    assert LLM_PROVIDER_ERROR == "llm.provider_error"
    assert LLM_BUDGET_EXCEEDED == "llm.budget_exceeded"
    assert ACCESS_DENIED == "access.denied"
    assert len(SECURITY_EVENTS) == 7


def test_alert_worthy_events_are_documented() -> None:
    docstring = security_logging.__doc__ or ""

    assert set(ALERT_WORTHY_EVENTS) <= SECURITY_EVENTS
    for event, condition in ALERT_WORTHY_EVENTS.items():
        assert event in docstring, f"{event} has no documented alert guidance"
        assert condition, f"{event} has an empty alert condition"


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_main_registers_the_processor_before_the_renderer() -> None:
    """Asserted on source text to avoid importing the whole app here."""
    source = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")

    assert "from app.services.security.logging import redact_sensitive" in source
    assert source.index("redact_sensitive,") < source.index("JSONRenderer()")
