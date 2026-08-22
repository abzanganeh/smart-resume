"""Security event taxonomy and PII-redacting structlog processor (M23 A3).

Covers OWASP **A09 — Security Logging and Monitoring Failures** and
**LLM02 — Sensitive Information Disclosure**.

Two problems are solved here:

1. *Under-logging.* Security-relevant refusals used to be logged with
   ad-hoc event names, so no alert rule could match them reliably. The
   constants below are the only names a router or service should emit for
   these situations, and :data:`SECURITY_EVENTS` is the closed set an
   alert pipeline can subscribe to.
2. *Over-logging.* The product handles résumé bodies, job descriptions,
   candidate email addresses, client IPs and provider API keys. None of
   that belongs in a log line that is shipped off-box.
   :func:`redact_sensitive` is a structlog processor that strips it from
   every record, whatever the call site did.

Alert-worthy events
-------------------

Every event in the taxonomy is worth *recording*; the ones below are
worth *waking someone up for*, at the rate at which they stop being
normal background noise. Thresholds are per-tenant unless noted.

``auth.login_failed``
    Credential stuffing / brute force. Alert on a spike for a single
    account (>10 in 5 min) or a single source IP prefix across accounts
    (>50 in 5 min). Individual events are expected and are not alerts.
``auth.signup_rate_limited``
    Automated account creation. Alert when the limiter trips repeatedly
    from one source (>20 in 15 min) — a signal of scripted signup abuse
    or disposable-address farming.
``billing.webhook_rejected``
    A Stripe webhook failed signature verification. Any sustained volume
    means either a leaked/rotated signing secret or a forgery attempt:
    page on >5 in 5 min. A single event after a deploy is usually a
    stale secret.
``billing.webhook_needs_review``
    A webhook exhausted its retries and was parked. Not an attack
    signal, but revenue-affecting and silent by nature: alert on any
    occurrence so a human drains the queue.
``llm.provider_error``
    Upstream model failures. Alert on an error rate above ~5% of calls
    over 5 min, or on any burst of ``401``/``403`` responses, which
    indicate a revoked or exfiltrated provider key.
``llm.budget_exceeded``
    A caller hit the per-request or per-plan token budget. Alert when one
    principal trips it repeatedly (>10 in 15 min) — the usual cause is
    quota-evasion or an unbounded retry loop.
``access.denied``
    An authenticated principal was refused a resource it does not own.
    Alert on >5 denials for one principal in 5 min: enumeration or a
    broken-object-level-authorization probe.

Redaction contract
------------------

The processor is intended to sit last in the chain before the renderer,
so it also covers fields injected by earlier processors and by
``structlog.contextvars``. It applies at *every* level — the requirement
is INFO and above, and redacting DEBUG too costs nothing because the app
filters DEBUG out anyway.

- Keys naming long-form candidate content (résumé, job description,
  prompts, completions, cover letters) are replaced wholesale; only the
  character count survives.
- Keys naming an email address are replaced by a keyed fingerprint, so
  two events from the same address can still be correlated without the
  address being present.
- Keys naming a client IP are masked to the /24 (IPv4) or /48 (IPv6)
  network, which keeps source-based alerting workable.
- Keys naming a credential are replaced by a fixed marker.
- Every *remaining* string value — including ``event`` and exception
  text, the usual accidental leak paths — is scanned for embedded email
  addresses, IP literals, provider key formats, bearer tokens and JWTs,
  and is truncated at :data:`MAX_VALUE_CHARS`.

Fingerprint correlation is keyed by ``SECURITY_LOG_HASH_SALT``. When it
is unset a random per-process salt is used, so fingerprints correlate
within one worker's lifetime but not across workers or restarts; set it
in the environment to correlate fleet-wide.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
from typing import Any, Final, MutableMapping

# ---------------------------------------------------------------------------
# Security event taxonomy
# ---------------------------------------------------------------------------

AUTH_LOGIN_FAILED: Final = "auth.login_failed"
AUTH_SIGNUP_RATE_LIMITED: Final = "auth.signup_rate_limited"
BILLING_WEBHOOK_REJECTED: Final = "billing.webhook_rejected"
BILLING_WEBHOOK_NEEDS_REVIEW: Final = "billing.webhook_needs_review"
LLM_PROVIDER_ERROR: Final = "llm.provider_error"
LLM_BUDGET_EXCEEDED: Final = "llm.budget_exceeded"
ACCESS_DENIED: Final = "access.denied"

SECURITY_EVENTS: Final[frozenset[str]] = frozenset(
    {
        AUTH_LOGIN_FAILED,
        AUTH_SIGNUP_RATE_LIMITED,
        BILLING_WEBHOOK_REJECTED,
        BILLING_WEBHOOK_NEEDS_REVIEW,
        LLM_PROVIDER_ERROR,
        LLM_BUDGET_EXCEEDED,
        ACCESS_DENIED,
    }
)

#: Events an on-call alert rule should subscribe to, mapped to the
#: condition that makes them actionable.  Documented in full in the
#: module docstring; kept as data so a future alert-config generator can
#: read it instead of parsing prose.
ALERT_WORTHY_EVENTS: Final[dict[str, str]] = {
    AUTH_LOGIN_FAILED: ">10 per account or >50 per source IP in 5 min",
    AUTH_SIGNUP_RATE_LIMITED: ">20 per source in 15 min",
    BILLING_WEBHOOK_REJECTED: ">5 in 5 min",
    BILLING_WEBHOOK_NEEDS_REVIEW: "any occurrence",
    LLM_PROVIDER_ERROR: ">5% of calls in 5 min, or any 401/403 burst",
    LLM_BUDGET_EXCEEDED: ">10 per principal in 15 min",
    ACCESS_DENIED: ">5 per principal in 5 min",
}

# ---------------------------------------------------------------------------
# Redaction configuration
# ---------------------------------------------------------------------------

#: Values longer than this are truncated.  Keeps a single log line from
#: carrying a whole document even when the key name is unrecognised.
MAX_VALUE_CHARS: Final = 512

#: Guards against pathological or cyclic structures reaching the renderer.
MAX_DEPTH: Final = 6

CONTENT_PLACEHOLDER: Final = "<redacted:content>"
SECRET_PLACEHOLDER: Final = "<redacted:secret>"
EMAIL_PLACEHOLDER: Final = "<redacted:email>"
IP_PLACEHOLDER: Final = "<redacted:ip>"
PHONE_PLACEHOLDER: Final = "<redacted:phone>"
NAME_PLACEHOLDER: Final = "<redacted:name>"

#: Keys whose value is long-form, user-supplied or model-generated text.
CONTENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "answer",
        "answers",
        "body",
        "bullet",
        "bullets",
        "chunk",
        "chunk_text",
        "chunks",
        "completion",
        "content",
        "cover_letter",
        "cover_letter_text",
        "description",
        "excerpt",
        "extracted_text",
        "jd",
        "jd_text",
        "job_description",
        "job_description_text",
        "master_resume",
        "message",
        "messages",
        "narrative",
        "note",
        "notes",
        "ocr_text",
        "parsed_text",
        "prompt",
        "prompt_text",
        "question",
        "raw",
        "raw_text",
        "response_text",
        "resume",
        "resume_text",
        "snippet",
        "story",
        "summary_text",
        "text",
        "transcript",
    }
)

#: Keys whose value is an email address.
EMAIL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "email",
        "email_address",
        "from_email",
        "recipient",
        "recipients",
        "reply_to",
        "to",
        "to_email",
        "user_email",
    }
)

#: Keys whose value is a client network address.
IP_KEYS: Final[frozenset[str]] = frozenset(
    {
        "client_ip",
        "forwarded_for",
        "ip",
        "ip_address",
        "peer_ip",
        "remote_addr",
        "remote_ip",
        "source_ip",
        "x_forwarded_for",
        "xff",
    }
)

#: Keys whose value is a credential, signature or key material.
SECRET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "access_token",
        "anthropic_api_key",
        "api_key",
        "apikey",
        "authorization",
        "byok_encryption_key",
        "client_secret",
        "cookie",
        "credentials",
        "dek",
        "encryption_key",
        "gemini_api_key",
        "google_api_key",
        "id_token",
        "kek",
        "openai_api_key",
        "password",
        "password_hash",
        "private_key",
        "provider_key",
        "recovery_codes",
        "refresh_token",
        "secret",
        "session_token",
        "set_cookie",
        "signature",
        "stripe_secret_key",
        "stripe_signature",
        "stripe_webhook_secret",
        "token",
        "totp_secret",
        "webhook_secret",
    }
)

#: Keys carrying other directly identifying contact details.
PHONE_KEYS: Final[frozenset[str]] = frozenset(
    {"phone", "phone_number", "sms_to", "to_phone"}
)

NAME_KEYS: Final[frozenset[str]] = frozenset(
    {"candidate_name", "first_name", "full_name", "last_name", "street_address"}
)

#: Keys structlog itself owns.  Their values are still string-scanned,
#: but they are never treated as content by key name — ``event`` in
#: particular must survive so alert rules can match on it.
RESERVED_KEYS: Final[frozenset[str]] = frozenset(
    {"event", "level", "logger", "timestamp"}
)

# Ordered alternation: the Anthropic form must be tried before the bare
# ``sk-`` form, and the replacement is identical either way.
_SECRET_PATTERN = re.compile(
    r"""(?x)
    sk-ant-[A-Za-z0-9\-_]{8,}
    | sk-(?:proj-)?[A-Za-z0-9\-_]{16,}
    | gsk_[A-Za-z0-9]{16,}
    | (?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}
    | whsec_[A-Za-z0-9+/=]{8,}
    | AIza[0-9A-Za-z\-_]{20,}
    | eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}
    | (?i:bearer)\s+[A-Za-z0-9\-._~+/=]{12,}
    """
)

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_IPV4_PATTERN = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")

_IPV6_PATTERN = re.compile(
    r"(?<![\w:])(?:[A-Fa-f0-9]{1,4}:){2,7}(?::|[A-Fa-f0-9]{1,4})(?![\w:])"
)

_HASH_SALT: Final[bytes] = (
    os.environ.get("SECURITY_LOG_HASH_SALT", "").encode("utf-8")
    or secrets.token_bytes(32)
)


def fingerprint(value: str) -> str:
    """Return a short keyed digest of ``value`` for correlation only.

    Keyed with ``SECURITY_LOG_HASH_SALT`` so the digest cannot be
    reversed by hashing a dictionary of candidate email addresses.
    """
    digest = hmac.new(_HASH_SALT, value.strip().lower().encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:12]


def mask_ip(value: str) -> str:
    """Mask an IP literal to its /24 (v4) or /48 (v6) network.

    Keeps source-based alerting and abuse correlation possible while
    dropping the host identity.  Anything that is not a parseable IP is
    replaced outright rather than passed through.
    """
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return IP_PLACEHOLDER
    prefix = 24 if address.version == 4 else 48
    network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    return str(network)


def _scrub_text(value: str) -> str:
    """Remove embedded secrets, addresses and IPs from a free-text value."""
    scrubbed = _SECRET_PATTERN.sub(SECRET_PLACEHOLDER, value)
    scrubbed = _EMAIL_PATTERN.sub(EMAIL_PLACEHOLDER, scrubbed)
    scrubbed = _IPV4_PATTERN.sub(
        lambda m: _mask_match(m.group(0)),
        scrubbed,
    )
    scrubbed = _IPV6_PATTERN.sub(
        lambda m: _mask_match(m.group(0)),
        scrubbed,
    )
    if len(scrubbed) > MAX_VALUE_CHARS:
        scrubbed = f"{scrubbed[:MAX_VALUE_CHARS]}…<truncated {len(scrubbed)} chars>"
    return scrubbed


def _mask_match(candidate: str) -> str:
    """Mask a regex-matched IP literal, leaving non-IP matches untouched.

    The IP patterns are deliberately loose so they cannot miss a real
    address; candidates :mod:`ipaddress` rejects (three-part version
    numbers, clock times) are handed back unchanged.  A four-octet
    version string is a valid IPv4 literal and so gets masked — an
    accepted false positive, since the alternative is missing real
    addresses.
    """
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return candidate
    return mask_ip(candidate)


def _redact_value(key: str, value: Any, depth: int) -> Any:
    normalized = key.lower()

    if depth > MAX_DEPTH:
        return "<redacted:nested>"

    if isinstance(value, dict):
        return {k: _redact_value(str(k), v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        items = [_redact_value(key, v, depth + 1) for v in value]
        return items if isinstance(value, list) else type(value)(items)

    if normalized not in RESERVED_KEYS:
        if normalized in SECRET_KEYS:
            return SECRET_PLACEHOLDER
        if normalized in EMAIL_KEYS:
            if isinstance(value, str) and value.strip():
                return f"<redacted:email:{fingerprint(value)}>"
            return EMAIL_PLACEHOLDER
        if normalized in IP_KEYS:
            return mask_ip(value) if isinstance(value, str) else IP_PLACEHOLDER
        if normalized in PHONE_KEYS:
            return PHONE_PLACEHOLDER
        if normalized in NAME_KEYS:
            return NAME_PLACEHOLDER
        if normalized in CONTENT_KEYS:
            if isinstance(value, str):
                return f"<redacted:content:{len(value)} chars>"
            return CONTENT_PLACEHOLDER

    if isinstance(value, str):
        return _scrub_text(value)
    return value


def redact_sensitive(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor that strips PII and credentials from a record.

    Place it immediately before the renderer so it also sees fields added
    by ``merge_contextvars`` and the other processors.  See the module
    docstring for the full contract.
    """
    return {key: _redact_value(str(key), value, 0) for key, value in event_dict.items()}


__all__ = [
    "ACCESS_DENIED",
    "ALERT_WORTHY_EVENTS",
    "AUTH_LOGIN_FAILED",
    "AUTH_SIGNUP_RATE_LIMITED",
    "BILLING_WEBHOOK_NEEDS_REVIEW",
    "BILLING_WEBHOOK_REJECTED",
    "LLM_BUDGET_EXCEEDED",
    "LLM_PROVIDER_ERROR",
    "SECURITY_EVENTS",
    "fingerprint",
    "mask_ip",
    "redact_sensitive",
]
