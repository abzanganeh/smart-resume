"""Subscription / Refund / Stripe-webhook / PlanConfig ORM models.

Mirrors the spec defined in:

- ``docs/SYSTEM_DESIGN_PHASE_2.md`` §18.3 (Subscription, RefundRecord)
- ``docs/IMPLEMENTATION_PLAN.md`` §7 (price_id resolution, 7-event webhook
  contract, idempotency table, grace-period state machine, PlanConfig)

These tables are introduced by Alembic migration ``0002_billing``.  Python
enums use ``create_type=False`` so the migration owns enum DDL — the model
layer never tries to (re)create types.

CreditTransaction (extended in ``user.py``) stays the *single source of
truth* for free / better / best balances per §7.5; this module declares
the surfaces it joins against.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# Python-side enums.  Names match the Postgres ENUM types created by
# ``alembic/versions/0002_billing.py``.
# ---------------------------------------------------------------------------


class SubscriptionPlan(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class SubscriptionBillingCycle(str, enum.Enum):
    recurring = "recurring"
    yearly = "yearly"


class LLMUpgradeTier(str, enum.Enum):
    standard = "standard"
    better = "better"
    best = "best"


class LLMUpgradeBillingCycle(str, enum.Enum):
    per_pack = "per_pack"
    monthly = "monthly"
    yearly = "yearly"


class SubscriptionStatus(str, enum.Enum):
    """Authoritative state set per IMPLEMENTATION_PLAN §7.6 grace-period
    machine.  ``cancelled`` from §18.3 is replaced by the more precise
    ``cancel_at_period_end`` introduced in §7.6."""

    trialing = "trialing"
    active = "active"
    grace = "grace"
    paused = "paused"
    cancelled = "cancelled"
    cancel_at_period_end = "cancel_at_period_end"
    expired = "expired"


class CreditKind(str, enum.Enum):
    """Credit ledger partition.

    - ``free``   — registration grant + admin compensation (§18.3 free tier).
    - ``better`` — Better LLM 5-pack purchases / consumptions (§7.5).
    - ``best``   — Best LLM per-resume purchases / consumptions (§7.5).
    """

    free = "free"
    better = "better"
    best = "best"


class RefundReason(str, enum.Enum):
    self_service_24h = "self_service_24h"
    self_service_unused = "self_service_unused"
    manual = "manual"
    chargeback = "chargeback"


class RefundInitiator(str, enum.Enum):
    user = "user"
    system = "system"
    admin = "admin"


class StripeWebhookStatus(str, enum.Enum):
    received = "received"
    processing = "processing"
    processed = "processed"
    failed = "failed"
    needs_review = "needs_review"


class PlanConfigInterval(str, enum.Enum):
    """Stripe-style recurrence label for the ``plan_configs`` row.

    ``one_time`` covers credit packs (better_5pack, best_per_resume).
    """

    day = "day"
    week = "week"
    month = "month"
    year = "year"
    one_time = "one_time"


# ---------------------------------------------------------------------------
# Postgres-side ENUM bindings (DDL owned by the migration).
# ---------------------------------------------------------------------------


def _pg_enum(py_enum: type[enum.Enum], name: str) -> PGEnum:
    return PGEnum(
        py_enum,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


_SUBSCRIPTION_PLAN_PG = _pg_enum(SubscriptionPlan, "subscription_plan")
_SUBSCRIPTION_BILLING_CYCLE_PG = _pg_enum(
    SubscriptionBillingCycle, "subscription_billing_cycle"
)
_LLM_UPGRADE_TIER_PG = _pg_enum(LLMUpgradeTier, "llm_upgrade_tier")
_LLM_UPGRADE_BILLING_CYCLE_PG = _pg_enum(
    LLMUpgradeBillingCycle, "llm_upgrade_billing_cycle"
)
_SUBSCRIPTION_STATUS_PG = _pg_enum(SubscriptionStatus, "subscription_status")
_CREDIT_KIND_PG = _pg_enum(CreditKind, "credit_kind")
_REFUND_REASON_PG = _pg_enum(RefundReason, "refund_reason")
_REFUND_INITIATOR_PG = _pg_enum(RefundInitiator, "refund_initiator")
_STRIPE_WEBHOOK_STATUS_PG = _pg_enum(
    StripeWebhookStatus, "stripe_webhook_status"
)
_PLAN_CONFIG_INTERVAL_PG = _pg_enum(PlanConfigInterval, "plan_config_interval")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


class Subscription(Base):
    """Per-user Stripe subscription row.

    All fields from SYSTEM_DESIGN_PHASE_2 §18.3, with the §7 additions
    needed by the webhook handler (``last_event_created_at`` for ordering,
    ``ended_at`` for terminal states, ``current_period_*`` to mirror Stripe).
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plan: Mapped[SubscriptionPlan] = mapped_column(
        _SUBSCRIPTION_PLAN_PG, nullable=False
    )
    billing_cycle: Mapped[SubscriptionBillingCycle] = mapped_column(
        _SUBSCRIPTION_BILLING_CYCLE_PG, nullable=False
    )
    llm_upgrade: Mapped[LLMUpgradeTier] = mapped_column(
        _LLM_UPGRADE_TIER_PG,
        nullable=False,
        default=LLMUpgradeTier.standard,
        server_default=LLMUpgradeTier.standard.value,
    )
    llm_upgrade_billing_cycle: Mapped[Optional[LLMUpgradeBillingCycle]] = (
        mapped_column(_LLM_UPGRADE_BILLING_CYCLE_PG, nullable=True)
    )

    status: Mapped[SubscriptionStatus] = mapped_column(
        _SUBSCRIPTION_STATUS_PG, nullable=False
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    resumes_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    searches_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    upgraded_resumes_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pause_resumes_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    payment_failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    stripe_customer_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Used by webhook ordering guard (§7.4): if an incoming event has
    # ``event.created < last_event_created_at`` we mark it processed without
    # mutation and emit ``out_of_order_skip``.
    last_event_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    refunds: Mapped[list["RefundRecord"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_subscriptions_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_subscriptions_grace_payment_failed_at",
            "status",
            "payment_failed_at",
        ),
    )

    @property
    def is_terminal(self) -> bool:
        return self.status == SubscriptionStatus.expired

    @property
    def grants_paid_access(self) -> bool:
        # §7.7 entitlement check used by quota.py.
        return self.status in {
            SubscriptionStatus.active,
            SubscriptionStatus.trialing,
            SubscriptionStatus.grace,
            SubscriptionStatus.cancel_at_period_end,
        }


# ---------------------------------------------------------------------------
# RefundRecord
# ---------------------------------------------------------------------------


class RefundRecord(Base):
    __tablename__ = "refund_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stripe_refund_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    amount_usd: Mapped[float] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    reason: Mapped[RefundReason] = mapped_column(
        _REFUND_REASON_PG, nullable=False
    )
    initiated_by: Mapped[RefundInitiator] = mapped_column(
        _REFUND_INITIATOR_PG, nullable=False
    )
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    subscription: Mapped[Optional["Subscription"]] = relationship(
        back_populates="refunds"
    )


# ---------------------------------------------------------------------------
# StripeWebhookEvent — idempotency + replay table (§7.4)
# ---------------------------------------------------------------------------


class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Stripe ``event.id``.  UNIQUE so duplicate deliveries become no-ops via
    # ``INSERT … ON CONFLICT (event_id) DO NOTHING``.
    event_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    livemode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[StripeWebhookStatus] = mapped_column(
        _STRIPE_WEBHOOK_STATUS_PG,
        nullable=False,
        default=StripeWebhookStatus.received,
        server_default=StripeWebhookStatus.received.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    related_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    related_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    created_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_stripe_webhook_status", "status"),
        Index("ix_stripe_webhook_type_created", "event_type", "created_event_at"),
    )


# ---------------------------------------------------------------------------
# PlanConfig — primary source of truth for stripe_price_id at runtime (§7.2)
# ---------------------------------------------------------------------------


class PlanConfig(Base):
    __tablename__ = "plan_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Canonical internal code (one of the 10 in IMPLEMENTATION_PLAN §7.1).
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_product_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    eligibility: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="USD", server_default="USD"
    )
    interval: Mapped[PlanConfigInterval] = mapped_column(
        _PLAN_CONFIG_INTERVAL_PG, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        # One active row per code at any given point in time.  ``effective_to``
        # is set on the prior row when admin updates pricing (§7.2 hardening).
        Index(
            "ix_plan_configs_code_active",
            "code",
            "is_active",
        ),
        UniqueConstraint(
            "stripe_price_id",
            name="uq_plan_configs_stripe_price_id",
        ),
    )


class NotificationChannel(str, enum.Enum):
    in_app = "in_app"
    email = "email"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class Notification(Base):
    """Minimal notification outbox row used by billing jobs.

    Step 31 will expand this model.  Step 6 needs a durable row so
    grace-expiry and trial reminders are persisted transactionally.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        _pg_enum(NotificationChannel, "notification_channel"),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        _pg_enum(NotificationStatus, "notification_status"),
        nullable=False,
        default=NotificationStatus.pending,
        server_default=NotificationStatus.pending.value,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )


class AdminAuditLog(Base):
    """Minimal admin audit row needed by billing failure paths.

    Step 35 introduces the full admin domain; this table shape is a
    compatible subset so Step 6 can already persist critical billing
    escalation actions.
    """

    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    before_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    after_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    ip: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    user_agent: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default=""
    )
    request_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )


__all__ = [
    "AdminAuditLog",
    "CreditKind",
    "LLMUpgradeBillingCycle",
    "LLMUpgradeTier",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "PlanConfig",
    "PlanConfigInterval",
    "RefundInitiator",
    "RefundReason",
    "RefundRecord",
    "StripeWebhookEvent",
    "StripeWebhookStatus",
    "Subscription",
    "SubscriptionBillingCycle",
    "SubscriptionPlan",
    "SubscriptionStatus",
]
