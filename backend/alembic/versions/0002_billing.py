"""billing: subscriptions, refunds, stripe webhook events, plan configs + credit_transactions extensions

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-31

Implements Step 6 of ``docs/IMPLEMENTATION_PLAN.md``:

- New ENUM types for subscription state machine, credit kinds, refund
  metadata, webhook status, plan-config interval (§7.4 + §7.6).
- ``subscriptions`` table — fields from SYSTEM_DESIGN_PHASE_2 §18.3 plus
  the IMPLEMENTATION_PLAN §7 additions ``ended_at`` and
  ``last_event_created_at`` used by the webhook ordering guard.
- ``refund_records`` table — §18.3 schema verbatim.
- ``stripe_webhook_events`` table — idempotency + replay storage from §7.4.
- ``plan_configs`` table — primary source of truth for stripe_price_id
  resolution (§7.2).
- ``credit_transactions`` extensions per §7.5: rename ``amount`` → ``delta``,
  add ``reason``, ``credit_kind``, ``stripe_event_id``,
  ``related_subscription_id``, ``related_resume_record_id``; add a partial
  unique index on ``(stripe_event_id, credit_kind)`` so duplicate webhook
  delivery is a no-op.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


SUBSCRIPTION_PLAN_ENUM = "subscription_plan"
SUBSCRIPTION_BILLING_CYCLE_ENUM = "subscription_billing_cycle"
LLM_UPGRADE_TIER_ENUM = "llm_upgrade_tier"
LLM_UPGRADE_BILLING_CYCLE_ENUM = "llm_upgrade_billing_cycle"
SUBSCRIPTION_STATUS_ENUM = "subscription_status"
CREDIT_KIND_ENUM = "credit_kind"
REFUND_REASON_ENUM = "refund_reason"
REFUND_INITIATOR_ENUM = "refund_initiator"
STRIPE_WEBHOOK_STATUS_ENUM = "stripe_webhook_status"
PLAN_CONFIG_INTERVAL_ENUM = "plan_config_interval"


def upgrade() -> None:
    bind = op.get_bind()

    # -------------------------------------------------------------------
    # ENUMs
    # -------------------------------------------------------------------
    enums = [
        postgresql.ENUM(
            "daily", "weekly", "monthly",
            name=SUBSCRIPTION_PLAN_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "recurring", "yearly",
            name=SUBSCRIPTION_BILLING_CYCLE_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "standard", "better", "best",
            name=LLM_UPGRADE_TIER_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "per_pack", "monthly", "yearly",
            name=LLM_UPGRADE_BILLING_CYCLE_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "trialing", "active", "grace", "paused",
            "cancel_at_period_end", "expired",
            name=SUBSCRIPTION_STATUS_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "free", "better", "best",
            name=CREDIT_KIND_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "self_service_24h", "self_service_unused", "manual", "chargeback",
            name=REFUND_REASON_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "user", "system", "admin",
            name=REFUND_INITIATOR_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "received", "processing", "processed", "failed", "needs_review",
            name=STRIPE_WEBHOOK_STATUS_ENUM,
            create_type=True,
        ),
        postgresql.ENUM(
            "day", "week", "month", "year", "one_time",
            name=PLAN_CONFIG_INTERVAL_ENUM,
            create_type=True,
        ),
    ]
    for e in enums:
        e.create(bind, checkfirst=True)

    # -------------------------------------------------------------------
    # subscriptions
    # -------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan",
            postgresql.ENUM(name=SUBSCRIPTION_PLAN_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column(
            "billing_cycle",
            postgresql.ENUM(name=SUBSCRIPTION_BILLING_CYCLE_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column(
            "llm_upgrade",
            postgresql.ENUM(name=LLM_UPGRADE_TIER_ENUM, create_type=False),
            nullable=False,
            server_default="standard",
        ),
        sa.Column(
            "llm_upgrade_billing_cycle",
            postgresql.ENUM(name=LLM_UPGRADE_BILLING_CYCLE_ENUM, create_type=False),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name=SUBSCRIPTION_STATUS_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resumes_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("searches_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "upgraded_resumes_used", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_resumes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
        sa.Column(
            "stripe_subscription_id", sa.String(length=255), nullable=False
        ),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=False),
        sa.Column(
            "last_event_created_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "stripe_subscription_id", name="uq_subscriptions_stripe_sub_id"
        ),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index(
        "ix_subscriptions_stripe_customer_id",
        "subscriptions",
        ["stripe_customer_id"],
    )
    op.create_index(
        "ix_subscriptions_user_status", "subscriptions", ["user_id", "status"]
    )
    op.create_index(
        "ix_subscriptions_grace_payment_failed_at",
        "subscriptions",
        ["status", "payment_failed_at"],
    )

    # -------------------------------------------------------------------
    # refund_records
    # -------------------------------------------------------------------
    op.create_table(
        "refund_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("stripe_refund_id", sa.String(length=255), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "reason",
            postgresql.ENUM(name=REFUND_REASON_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column(
            "initiated_by",
            postgresql.ENUM(name=REFUND_INITIATOR_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "stripe_refund_id", name="uq_refund_records_stripe_refund_id"
        ),
    )
    op.create_index("ix_refund_records_user_id", "refund_records", ["user_id"])
    op.create_index(
        "ix_refund_records_subscription_id",
        "refund_records",
        ["subscription_id"],
    )

    # -------------------------------------------------------------------
    # stripe_webhook_events  (§7.4 — idempotency + replay)
    # -------------------------------------------------------------------
    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column(
            "livemode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name=STRIPE_WEBHOOK_STATUS_ENUM, create_type=False),
            nullable=False,
            server_default="received",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "related_subscription_id", sa.String(length=255), nullable=True
        ),
        sa.Column("related_customer_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_event_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.UniqueConstraint("event_id", name="uq_stripe_webhook_events_event_id"),
    )
    op.create_index(
        "ix_stripe_webhook_events_event_id",
        "stripe_webhook_events",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_stripe_webhook_events_related_subscription_id",
        "stripe_webhook_events",
        ["related_subscription_id"],
    )
    op.create_index(
        "ix_stripe_webhook_events_related_customer_id",
        "stripe_webhook_events",
        ["related_customer_id"],
    )
    op.create_index(
        "ix_stripe_webhook_status",
        "stripe_webhook_events",
        ["status"],
    )
    op.create_index(
        "ix_stripe_webhook_type_created",
        "stripe_webhook_events",
        ["event_type", "created_event_at"],
    )

    # -------------------------------------------------------------------
    # plan_configs  (§7.2 — primary source of truth for stripe_price_id)
    # -------------------------------------------------------------------
    op.create_table(
        "plan_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_product_id", sa.String(length=255), nullable=True),
        sa.Column(
            "amount_cents", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
            server_default="USD",
        ),
        sa.Column(
            "interval",
            postgresql.ENUM(name=PLAN_CONFIG_INTERVAL_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "stripe_price_id", name="uq_plan_configs_stripe_price_id"
        ),
    )
    op.create_index("ix_plan_configs_code", "plan_configs", ["code"])
    op.create_index(
        "ix_plan_configs_code_active", "plan_configs", ["code", "is_active"]
    )

    # -------------------------------------------------------------------
    # credit_transactions extensions  (§7.5)
    # -------------------------------------------------------------------
    # Rename ``amount`` → ``delta`` to match §7.5 semantics.
    op.alter_column(
        "credit_transactions",
        "amount",
        new_column_name="delta",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # New columns: reason (free-form), credit_kind, stripe_event_id, related_*.
    op.add_column(
        "credit_transactions",
        sa.Column(
            "reason",
            sa.String(length=120),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "credit_transactions",
        sa.Column(
            "credit_kind",
            postgresql.ENUM(name=CREDIT_KIND_ENUM, create_type=False),
            nullable=False,
            server_default="free",
        ),
    )
    op.add_column(
        "credit_transactions",
        sa.Column("stripe_event_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "credit_transactions",
        sa.Column(
            "related_subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "credit_transactions",
        sa.Column(
            "related_resume_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # Backfill ``reason`` from ``action`` for any rows that already exist
    # (registration grants from Step 3).  This is data-safe because
    # ``action.value`` is always a stable string.
    op.execute(
        "UPDATE credit_transactions SET reason = action::text WHERE reason = ''"
    )

    # §7.5 — partial UNIQUE so duplicate webhook delivery is a no-op.
    # WHERE clause filters NULL stripe_event_id so registration grants
    # (stripe_event_id IS NULL) don't collide.
    op.create_index(
        "uq_credit_tx_stripe_event_kind",
        "credit_transactions",
        ["stripe_event_id", "credit_kind"],
        unique=True,
        postgresql_where=sa.text("stripe_event_id IS NOT NULL"),
    )
    op.create_index(
        "ix_credit_transactions_user_kind",
        "credit_transactions",
        ["user_id", "credit_kind"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_credit_transactions_user_kind", table_name="credit_transactions"
    )
    op.drop_index(
        "uq_credit_tx_stripe_event_kind", table_name="credit_transactions"
    )
    op.drop_column("credit_transactions", "related_resume_record_id")
    op.drop_column("credit_transactions", "related_subscription_id")
    op.drop_column("credit_transactions", "stripe_event_id")
    op.drop_column("credit_transactions", "credit_kind")
    op.drop_column("credit_transactions", "reason")
    op.alter_column(
        "credit_transactions",
        "delta",
        new_column_name="amount",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.drop_index("ix_plan_configs_code_active", table_name="plan_configs")
    op.drop_index("ix_plan_configs_code", table_name="plan_configs")
    op.drop_table("plan_configs")

    op.drop_index(
        "ix_stripe_webhook_type_created", table_name="stripe_webhook_events"
    )
    op.drop_index("ix_stripe_webhook_status", table_name="stripe_webhook_events")
    op.drop_index(
        "ix_stripe_webhook_events_related_customer_id",
        table_name="stripe_webhook_events",
    )
    op.drop_index(
        "ix_stripe_webhook_events_related_subscription_id",
        table_name="stripe_webhook_events",
    )
    op.drop_index(
        "ix_stripe_webhook_events_event_id", table_name="stripe_webhook_events"
    )
    op.drop_table("stripe_webhook_events")

    op.drop_index("ix_refund_records_subscription_id", table_name="refund_records")
    op.drop_index("ix_refund_records_user_id", table_name="refund_records")
    op.drop_table("refund_records")

    op.drop_index(
        "ix_subscriptions_grace_payment_failed_at", table_name="subscriptions"
    )
    op.drop_index("ix_subscriptions_user_status", table_name="subscriptions")
    op.drop_index(
        "ix_subscriptions_stripe_customer_id", table_name="subscriptions"
    )
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    bind = op.get_bind()
    for name in (
        PLAN_CONFIG_INTERVAL_ENUM,
        STRIPE_WEBHOOK_STATUS_ENUM,
        REFUND_INITIATOR_ENUM,
        REFUND_REASON_ENUM,
        CREDIT_KIND_ENUM,
        SUBSCRIPTION_STATUS_ENUM,
        LLM_UPGRADE_BILLING_CYCLE_ENUM,
        LLM_UPGRADE_TIER_ENUM,
        SUBSCRIPTION_BILLING_CYCLE_ENUM,
        SUBSCRIPTION_PLAN_ENUM,
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
