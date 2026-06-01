"""notifications platform: expand notifications, preferences, web push

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-31

Implements Step 31 of ``docs/IMPLEMENTATION_PLAN.md`` and
``SYSTEM_DESIGN_PHASE_2.md`` §19.5.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

NOTIFICATION_CHANNEL_ENUM = "notification_channel"
NOTIFICATION_DELIVERY_ENUM = "notification_delivery_status"
DIGEST_MODE_ENUM = "notification_digest_mode"


def upgrade() -> None:
    bind = op.get_bind()

    # Extend channel enum (in_app, email already exist from 0002).
    for value in ("web_push", "sms", "multi"):
        op.execute(
            sa.text(
                f"ALTER TYPE {NOTIFICATION_CHANNEL_ENUM} "
                f"ADD VALUE IF NOT EXISTS '{value}'"
            )
        )

    # New delivery-status enum (replaces notification_status on the table).
    delivery = postgresql.ENUM(
        "pending",
        "sent",
        "delivered",
        "bounced",
        "failed",
        name=NOTIFICATION_DELIVERY_ENUM,
        create_type=True,
    )
    delivery.create(bind, checkfirst=True)

    digest = postgresql.ENUM(
        "off",
        "daily",
        name=DIGEST_MODE_ENUM,
        create_type=True,
    )
    digest.create(bind, checkfirst=True)

    # Expand notifications table (created in 0002; scheduled_at from 0010).
    op.add_column(
        "notifications",
        sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
    )
    op.add_column(
        "notifications",
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "notifications",
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "delivery_status",
            postgresql.ENUM(name=NOTIFICATION_DELIVERY_ENUM, create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "notifications",
        sa.Column("error", sa.Text(), nullable=True),
    )

    # Backfill from legacy columns.
    op.execute(
        sa.text(
            """
            UPDATE notifications SET
              data = COALESCE(payload, '{}'::jsonb),
              title = COALESCE(
                NULLIF(payload->>'headline', ''),
                NULLIF(payload->>'title', ''),
                REPLACE(type, '_', ' ')
              ),
              body = COALESCE(payload->>'body', ''),
              delivery_status = CASE status::text
                WHEN 'pending' THEN 'pending'
                WHEN 'sent' THEN 'sent'
                WHEN 'failed' THEN 'failed'
                ELSE 'pending'
              END::notification_delivery_status,
              category = CASE
                WHEN type LIKE 'application_%' THEN 'application'
                WHEN type LIKE 'subscription_%' THEN 'subscription'
                WHEN type LIKE 'payment_%' THEN 'payment'
                ELSE 'general'
              END
            """
        )
    )

    op.alter_column("notifications", "delivery_status", nullable=False)
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_column("notifications", "status")
    op.drop_column("notifications", "payload")

    op.create_index(
        "ix_notifications_delivery_status",
        "notifications",
        ["delivery_status"],
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "read_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_pending_dispatch",
        "notifications",
        ["scheduled_at", "delivery_status"],
        postgresql_where=sa.text(
            "scheduled_at IS NOT NULL AND sent_at IS NULL "
            "AND delivery_status = 'pending'"
        ),
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "email_enabled_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "in_app_enabled_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "web_push_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sms_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sms_phone", sa.String(length=32), nullable=True),
        sa.Column("sms_phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "digest_mode",
            postgresql.ENUM(name=DIGEST_MODE_ENUM, create_type=False),
            nullable=False,
            server_default="off",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_notification_preferences_user_id",
        "notification_preferences",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "web_push_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("expiration_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("user_agent", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("platform_hint", sa.String(length=64), nullable=False, server_default=""),
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
        sa.UniqueConstraint("user_id", "endpoint", name="uq_web_push_user_endpoint"),
    )
    op.create_index(
        "ix_web_push_subscriptions_user_id",
        "web_push_subscriptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_web_push_subscriptions_user_id", table_name="web_push_subscriptions")
    op.drop_table("web_push_subscriptions")
    op.drop_index(
        "ix_notification_preferences_user_id",
        table_name="notification_preferences",
    )
    op.drop_table("notification_preferences")

    op.add_column(
        "notifications",
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "status",
            postgresql.ENUM(name="notification_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE notifications SET
              payload = data,
              status = CASE delivery_status::text
                WHEN 'sent' THEN 'sent'
                WHEN 'failed' THEN 'failed'
                WHEN 'bounced' THEN 'failed'
                ELSE 'pending'
              END::notification_status
            """
        )
    )
    op.drop_index("ix_notifications_pending_dispatch", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_delivery_status", table_name="notifications")
    op.drop_column("notifications", "error")
    op.drop_column("notifications", "delivery_status")
    op.drop_column("notifications", "sent_at")
    op.drop_column("notifications", "read_at")
    op.drop_column("notifications", "data")
    op.drop_column("notifications", "body")
    op.drop_column("notifications", "title")
    op.drop_column("notifications", "category")
    op.create_index("ix_notifications_status", "notifications", ["status"])

    op.execute(sa.text(f"DROP TYPE IF EXISTS {DIGEST_MODE_ENUM}"))
    op.execute(sa.text(f"DROP TYPE IF EXISTS {NOTIFICATION_DELIVERY_ENUM}"))
