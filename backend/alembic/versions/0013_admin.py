"""admin: admin_users, admin_invites, feature_flags, announcements; harden admin_audit_log

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-31

Implements Step 35 of ``docs/IMPLEMENTATION_PLAN.md`` (Admin Identity +
Admin Domain Models + Admin APIs).  IMPLEMENTATION_PLAN §5 names this
migration ``0010_admin`` but the project has already shipped 0001-0012
due to inserted milestones; this migration is the authoritative
``admin`` migration referenced by §8.4.

Tables created:

- ``admin_users``      — AdminUser per §19.7 / §8.4.1.
- ``admin_invites``    — invite-flow tokens (super-admin → invited admin).
- ``feature_flags``    — admin-managed boolean toggles per §19.7 #3.
- ``announcements``    — admin banners per §19.7 #4.

Tables modified:

- ``admin_audit_log``  — harden to append-only via ``REVOKE UPDATE,
  DELETE`` on the application role (§8.4.4).

``plan_configs`` and ``llm_configs`` already exist (created by 0002 and
0006 respectively) and need no further DDL here.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


ADMIN_ROLE_ENUM = "admin_role"
ANNOUNCEMENT_SEVERITY_ENUM = "announcement_severity"
ANNOUNCEMENT_AUDIENCE_ENUM = "announcement_audience"
FEATURE_FLAG_VISIBILITY_ENUM = "feature_flag_visibility"


def _app_role() -> str:
    """Return the application DB role used by the runtime backend.

    The REVOKE statement targets *that* role so the migration is
    correct in any deployment naming scheme.  Defaults to
    ``smart_resume_app_user`` per IMPLEMENTATION_PLAN §8.4.4 but can
    be overridden via ``SMART_RESUME_APP_ROLE`` for local Docker setups
    where the runtime user matches the database owner.
    """
    return os.environ.get("SMART_RESUME_APP_ROLE", "smart_resume_app_user")


def upgrade() -> None:
    bind = op.get_bind()

    # -------------------------------------------------------------------
    # ENUMs
    # -------------------------------------------------------------------
    role_enum = postgresql.ENUM(
        "super_admin",
        "admin",
        "support_agent",
        "read_only_analyst",
        name=ADMIN_ROLE_ENUM,
        create_type=True,
    )
    severity_enum = postgresql.ENUM(
        "info",
        "warning",
        "critical",
        "maintenance",
        name=ANNOUNCEMENT_SEVERITY_ENUM,
        create_type=True,
    )
    audience_enum = postgresql.ENUM(
        "all",
        "subscribed",
        "admin",
        name=ANNOUNCEMENT_AUDIENCE_ENUM,
        create_type=True,
    )
    visibility_enum = postgresql.ENUM(
        "public",
        "internal",
        name=FEATURE_FLAG_VISIBILITY_ENUM,
        create_type=True,
    )
    for e in (role_enum, severity_enum, audience_enum, visibility_enum):
        e.create(bind, checkfirst=True)

    # -------------------------------------------------------------------
    # admin_users
    # -------------------------------------------------------------------
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "role",
            postgresql.ENUM(name=ADMIN_ROLE_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("totp_secret", sa.LargeBinary(), nullable=True),
        sa.Column(
            "totp_recovery_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "must_enroll_2fa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_via",
            sa.String(length=32),
            nullable=False,
            server_default="invite",
        ),
        sa.Column(
            "created_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"])
    op.create_index("ix_admin_users_role", "admin_users", ["role"])

    # -------------------------------------------------------------------
    # admin_invites
    # -------------------------------------------------------------------
    op.create_table(
        "admin_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name=ADMIN_ROLE_ENUM, create_type=False),
            nullable=False,
        ),
        # SHA-256 hex of the opaque invite token (the plaintext only ever
        # leaves the backend in the invite email URL).
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "invited_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("token_hash", name="uq_admin_invites_token_hash"),
    )
    op.create_index("ix_admin_invites_email", "admin_invites", ["email"])
    op.create_index(
        "ix_admin_invites_pending",
        "admin_invites",
        ["email"],
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    # -------------------------------------------------------------------
    # feature_flags
    # -------------------------------------------------------------------
    op.create_table(
        "feature_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "rollout_percent",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
        sa.Column("variant", sa.String(length=80), nullable=True),
        sa.Column(
            "allowlist_emails",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "blocklist_emails",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "visibility",
            postgresql.ENUM(name=FEATURE_FLAG_VISIBILITY_ENUM, create_type=False),
            nullable=False,
            server_default="public",
        ),
        sa.Column(
            "updated_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint("key", name="uq_feature_flags_key"),
        sa.CheckConstraint(
            "rollout_percent BETWEEN 0 AND 100",
            name="ck_feature_flags_rollout_pct",
        ),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"])

    # -------------------------------------------------------------------
    # announcements
    # -------------------------------------------------------------------
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "severity",
            postgresql.ENUM(name=ANNOUNCEMENT_SEVERITY_ENUM, create_type=False),
            nullable=False,
            server_default="info",
        ),
        sa.Column(
            "audience",
            postgresql.ENUM(name=ANNOUNCEMENT_AUDIENCE_ENUM, create_type=False),
            nullable=False,
            server_default="all",
        ),
        sa.Column("cta_label", sa.String(length=120), nullable=True),
        sa.Column("cta_url", sa.String(length=2048), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint("slug", name="uq_announcements_slug"),
        sa.CheckConstraint(
            "ends_at >= starts_at",
            name="ck_announcements_window",
        ),
    )
    op.create_index("ix_announcements_window", "announcements", ["starts_at", "ends_at"])
    op.create_index("ix_announcements_audience", "announcements", ["audience"])

    # -------------------------------------------------------------------
    # admin_audit_log: actor_admin_id -> admin_users.id (was unconstrained
    # since 0002 because admin_users did not exist yet); add useful
    # filter indexes; harden as append-only via REVOKE.
    # -------------------------------------------------------------------
    # Create the FK as NOT VALID-friendly via add_column? It already
    # exists; just add the constraint.  Use ON DELETE SET NULL so an
    # admin row deletion keeps history.
    op.create_foreign_key(
        "fk_admin_audit_log_actor",
        "admin_audit_log",
        "admin_users",
        ["actor_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_admin_audit_log_actor",
        "admin_audit_log",
        ["actor_admin_id", "created_at"],
    )
    op.create_index(
        "ix_admin_audit_log_target",
        "admin_audit_log",
        ["target_kind", "target_id"],
    )

    # Append-only protection (§8.4.4).  We only revoke if the role exists
    # — local Docker setups often run as the DB owner and have no
    # separate ``smart_resume_app_user`` role.  The migration must stay
    # idempotent in those environments.
    role_name = _app_role()
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role_name}') THEN
                    EXECUTE 'REVOKE UPDATE, DELETE ON admin_audit_log FROM "{role_name}"';
                END IF;
            END
            $$;
            """
        )
    )

    # Belt-and-braces: install a row-level trigger that aborts any
    # UPDATE/DELETE attempt regardless of which role is connected.  This
    # is the layer the test_audit_append_only.py test asserts because
    # the per-role grant is environment-specific.
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION admin_audit_log_block_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'admin_audit_log is append-only (% blocked)', TG_OP
                  USING ERRCODE = 'insufficient_privilege';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER admin_audit_log_no_update
            BEFORE UPDATE ON admin_audit_log
            FOR EACH ROW EXECUTE FUNCTION admin_audit_log_block_mutation();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER admin_audit_log_no_delete
            BEFORE DELETE ON admin_audit_log
            FOR EACH ROW EXECUTE FUNCTION admin_audit_log_block_mutation();
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS admin_audit_log_no_delete ON admin_audit_log"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS admin_audit_log_no_update ON admin_audit_log"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS admin_audit_log_block_mutation()"))

    op.drop_index("ix_admin_audit_log_target", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_actor", table_name="admin_audit_log")
    op.drop_constraint(
        "fk_admin_audit_log_actor", "admin_audit_log", type_="foreignkey"
    )

    op.drop_index("ix_announcements_audience", table_name="announcements")
    op.drop_index("ix_announcements_window", table_name="announcements")
    op.drop_table("announcements")

    op.drop_index("ix_feature_flags_key", table_name="feature_flags")
    op.drop_table("feature_flags")

    op.drop_index("ix_admin_invites_pending", table_name="admin_invites")
    op.drop_index("ix_admin_invites_email", table_name="admin_invites")
    op.drop_table("admin_invites")

    op.drop_index("ix_admin_users_role", table_name="admin_users")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")

    bind = op.get_bind()
    for name in (
        FEATURE_FLAG_VISIBILITY_ENUM,
        ANNOUNCEMENT_AUDIENCE_ENUM,
        ANNOUNCEMENT_SEVERITY_ENUM,
        ADMIN_ROLE_ENUM,
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
