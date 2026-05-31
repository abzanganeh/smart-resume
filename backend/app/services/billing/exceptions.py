"""Typed billing-service errors.

The router layer translates these into HTTP responses; the service layer
never imports FastAPI HTTPException so it stays testable and reusable.
"""

from __future__ import annotations


class BillingError(Exception):
    """Base class for all billing-service errors."""


class PriceUnresolvedError(BillingError):
    """Neither ``PlanConfig`` nor env fallback knows about ``code``.

    Translated to HTTP 503 ``price_unresolved`` per IMPLEMENTATION_PLAN §7.2.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"price unresolved for code={code!r}")
        self.code = code


class InsufficientCreditsError(BillingError):
    """Credit balance is zero/negative for the requested kind.

    Translated to HTTP 402 ``insufficient_credits`` per §7.5 and §18.3.
    """

    def __init__(self, credit_kind: str, balance: int) -> None:
        super().__init__(
            f"insufficient credits (kind={credit_kind!r}, balance={balance})"
        )
        self.credit_kind = credit_kind
        self.balance = balance


class SubscriptionRequiredError(BillingError):
    """Action is gated behind a paid subscription.

    Translated to HTTP 402 ``subscription_required`` from quota routing
    (§18.3 routing tree).
    """

    def __init__(self, action: str) -> None:
        super().__init__(f"subscription required for action={action!r}")
        self.action = action


class AccountSuspendedError(BillingError):
    """Quota check denied because the user is suspended.

    Translated to HTTP 403 ``account_suspended``.
    """


class PlanLimitReachedError(BillingError):
    """User is subscribed but has exhausted the period quota.

    Translated to HTTP 402 ``plan_limit_reached``.
    """

    def __init__(self, action: str, used: int, limit: int) -> None:
        super().__init__(
            f"plan limit reached for action={action!r} ({used}/{limit})"
        )
        self.action = action
        self.used = used
        self.limit = limit


class BillingCycleMismatchError(BillingError):
    """Yearly LLM add-on requires a yearly base subscription.

    Translated to HTTP 409 ``billing_cycle_mismatch`` per §7.7.
    """


class WebhookSignatureError(BillingError):
    """``stripe.Webhook.construct_event`` rejected the request body.

    Translated to HTTP 400 ``invalid_signature`` (§7.4).
    """


class WebhookPayloadError(BillingError):
    """Verified webhook is missing required fields or references an
    unknown price ID.  We park the row in ``needs_review`` rather than
    crashing or silently granting credits (§7.2 hardening)."""


__all__ = [
    "AccountSuspendedError",
    "BillingCycleMismatchError",
    "BillingError",
    "InsufficientCreditsError",
    "PlanLimitReachedError",
    "PriceUnresolvedError",
    "SubscriptionRequiredError",
    "WebhookPayloadError",
    "WebhookSignatureError",
]
