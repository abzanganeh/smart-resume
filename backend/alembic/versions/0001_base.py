"""base: pgvector + identity tables (users, refresh_tokens, auth_audit_log, credit_transactions)

Revision ID: 0001
Revises:
Create Date: 2026-05-30

Per `docs/IMPLEMENTATION_PLAN.md` §5, ``0001_base`` carries:

- the ``vector`` extension (needed by every subsequent vector column);
- core enums shared across the identity / billing surface;
- the ``users`` table from SYSTEM_DESIGN_PHASE_2 §18.2;
- the ``refresh_tokens`` table from §18.2;
- the ``auth_audit_log`` table from §19.7;
- a minimal ``credit_transactions`` table so the registration grant
  (Step 3 acceptance criterion) can be inserted in the same transaction
  as the user row. Step 6 (``0002_billing``) extends this surface with
  ``subscriptions`` and ``refund_records``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


# ---------------------------------------------------------------------------
# Enum names (created once; reused in later migrations).
# ---------------------------------------------------------------------------
USER_AUTH_PROVIDER_ENUM = "user_auth_provider"
USER_TIER_ENUM = "user_tier"
AUTH_AUDIT_EVENT_ENUM = "auth_audit_event"
CREDIT_TX_ACTION_ENUM = "credit_transaction_action"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -------------------------------------------------------------------
    # Enums
    # -------------------------------------------------------------------
    auth_provider = postgresql.ENUM(
        "email",
        "google",
        "github",
        name=USER_AUTH_PROVIDER_ENUM,
        create_type=True,
    )
    user_tier = postgresql.ENUM(
        "free",
        "pro",
        name=USER_TIER_ENUM,
        create_type=True,
    )
    auth_event = postgresql.ENUM(
        "login_success",
        "login_failure",
        "logout",
        "password_reset",
        "2fa_enroll",
        "2fa_disable",
        "suspicious_login",
        "account_locked",
        name=AUTH_AUDIT_EVENT_ENUM,
        create_type=True,
    )
    credit_action = postgresql.ENUM(
        "registration_grant",
        "resume_build",
        "ats_recalc",
        "cover_letter",
        "section_regen",
        "llm_upgrade_pack",
        "llm_upgrade_pack_use",
        "admin_grant",
        "admin_revoke",
        "refund_reverse",
        name=CREDIT_TX_ACTION_ENUM,
        create_type=True,
    )
    bind = op.get_bind()
    for enum in (auth_provider, user_tier, auth_event, credit_action):
        enum.create(bind, checkfirst=True)

    # -------------------------------------------------------------------
    # users
    # -------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "auth_provider",
            postgresql.ENUM(name=USER_AUTH_PROVIDER_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("provider_id", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "tier",
            postgresql.ENUM(name=USER_TIER_ENUM, create_type=False),
            nullable=False,
            server_default="free",
        ),
        sa.Column(
            "credit_balance",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("byok_api_key", sa.LargeBinary(), nullable=True),
        sa.Column("byok_provider", sa.String(length=64), nullable=True),
        sa.Column("byok_key_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("totp_secret", sa.LargeBinary(), nullable=True),
        sa.Column(
            "totp_recovery_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("trials_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closure_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspension_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "accepted_tos_version",
            sa.String(length=32),
            nullable=False,
            server_default="",
        ),
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "blocked_companies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index(
        "ix_users_provider_identity",
        "users",
        ["auth_provider", "provider_id"],
        unique=False,
    )

    # -------------------------------------------------------------------
    # refresh_tokens
    # -------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("device_fingerprint", sa.String(length=128), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )

    # -------------------------------------------------------------------
    # auth_audit_log
    # -------------------------------------------------------------------
    op.create_table(
        "auth_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "event",
            postgresql.ENUM(name=AUTH_AUDIT_EVENT_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=512), nullable=False, server_default=""),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_auth_audit_log_user_event_time",
        "auth_audit_log",
        ["user_id", "event", "created_at"],
    )
    op.create_index(
        "ix_auth_audit_log_created_at",
        "auth_audit_log",
        ["created_at"],
    )

    # -------------------------------------------------------------------
    # credit_transactions (minimal; Step 6 / 0002_billing fills out the
    # billing surface — Subscription, RefundRecord, indices, etc.).
    # -------------------------------------------------------------------
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "action",
            postgresql.ENUM(name=CREDIT_TX_ACTION_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_credit_transactions_user_id",
        "credit_transactions",
        ["user_id"],
    )


def downgrade() -> None:
    # Tables first (FK order), then enums, then the extension. The
    # extension drop is intentionally a no-op: dropping ``vector`` would
    # destroy any data using it in databases shared across migrations.
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")

    op.drop_index("ix_auth_audit_log_created_at", table_name="auth_audit_log")
    op.drop_index("ix_auth_audit_log_user_event_time", table_name="auth_audit_log")
    op.drop_table("auth_audit_log")

    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_provider_identity", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    for name in (
        CREDIT_TX_ACTION_ENUM,
        AUTH_AUDIT_EVENT_ENUM,
        USER_TIER_ENUM,
        USER_AUTH_PROVIDER_ENUM,
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
