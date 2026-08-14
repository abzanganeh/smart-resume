"""admin_user_grants: admin-issued user entitlements

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ADMIN_GRANT_TYPE_ENUM = "admin_grant_type"


def upgrade() -> None:
    grant_type_enum = postgresql.ENUM(
        "extra_credits",
        "tier_override",
        "feature_unlock",
        name=ADMIN_GRANT_TYPE_ENUM,
        create_type=True,
    )
    grant_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "admin_user_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grant_type",
            postgresql.ENUM(
                "extra_credits",
                "tier_override",
                "feature_unlock",
                name=ADMIN_GRANT_TYPE_ENUM,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_admin_user_grants_user_id",
        "admin_user_grants",
        ["user_id"],
    )
    op.create_index(
        "ix_admin_user_grants_user_active",
        "admin_user_grants",
        ["user_id", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_user_grants_user_active", table_name="admin_user_grants")
    op.drop_index("ix_admin_user_grants_user_id", table_name="admin_user_grants")
    op.drop_table("admin_user_grants")
    postgresql.ENUM(name=ADMIN_GRANT_TYPE_ENUM).drop(op.get_bind(), checkfirst=True)
