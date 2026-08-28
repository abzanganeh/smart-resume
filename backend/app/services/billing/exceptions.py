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


class FreeTierAiBudgetExceededError(InsufficientCreditsError):
    """Free-tier lifetime platform AI-spend cap reached.

    Distinct subclass so ``orchestrator._classify_error`` can route this
    to a user-facing ``free_tier_ai_cap_reached`` message with an
    upgrade CTA — the generic "AI service is out of credit on our side"
    copy is wrong for a per-user quota and blocks retries indefinitely.
    """

    def __init__(self, *, cap_usd: float, used_usd: float) -> None:
        super().__init__("free", 0)
        self.cap_usd = cap_usd
        self.used_usd = used_usd


FREE_TIER_AI_CAP_CODE = "free_tier_ai_cap_reached"
FREE_TIER_AI_CAP_MESSAGE = (
    "You've used up the free-plan AI allowance for your account. "
    "Upgrade to a paid plan to keep tailoring — retrying will not help."
)


def free_tier_ai_cap_detail() -> dict[str, str]:
    return {"code": FREE_TIER_AI_CAP_CODE, "message": FREE_TIER_AI_CAP_MESSAGE}


class CreditsLockedUntilVerificationError(BillingError):
    """Free credits exist but email is not verified yet.

    Translated to HTTP 403 ``credits_locked_until_verification``.
    """

    def __init__(self, *, balance: int) -> None:
        super().__init__(
            f"free credits locked until email verification (balance={balance})"
        )
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


class WhisperNotAllowedError(BillingError):
    """Whisper transcription is not included on the user's tier.

    Translated to HTTP 402 ``whisper_not_available``.
    """

    def __init__(self, *, plan_code: str) -> None:
        super().__init__(f"whisper not available for plan={plan_code!r}")
        self.plan_code = plan_code


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


class SubscriptionPauseNotAllowedError(BillingError):
    """Pause is requested for a plan whose cycle does not support pausing.

    Per §19.8 only Monthly + Yearly cycles can be paused; Daily/Weekly
    plans are too short-lived for the 7-day minimum window.  Routers
    translate this to HTTP 422 ``pause_not_allowed`` so the frontend
    can hide the pause button on those plans.
    """

    def __init__(self, plan: str, billing_cycle: str) -> None:
        super().__init__(
            f"pause not allowed for plan={plan!r} cycle={billing_cycle!r}"
        )
        self.plan = plan
        self.billing_cycle = billing_cycle


class RefundError(BillingError):
    """Refund workflow could not be completed.

    Routers translate this to HTTP 400 ``refund_failed``.  Carries the
    ``stage`` (``stripe`` / ``ledger`` / ``email``) so the admin UI can
    show which step failed.
    """

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"refund failed at {stage}: {message}")
        self.stage = stage
        self.message = message


__all__ = [
    "AccountSuspendedError",
    "BillingCycleMismatchError",
    "BillingError",
    "CreditsLockedUntilVerificationError",
    "FreeTierAiBudgetExceededError",
    "FREE_TIER_AI_CAP_CODE",
    "FREE_TIER_AI_CAP_MESSAGE",
    "free_tier_ai_cap_detail",
    "InsufficientCreditsError",
    "PlanLimitReachedError",
    "PriceUnresolvedError",
    "RefundError",
    "SubscriptionPauseNotAllowedError",
    "SubscriptionRequiredError",
    "WebhookPayloadError",
    "WebhookSignatureError",
]
