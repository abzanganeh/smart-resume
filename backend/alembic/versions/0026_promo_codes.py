"""promo_codes and promo_redemptions tables

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ADMIN_GRANT_TYPE_ENUM = "admin_grant_type"


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
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
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column(
            "redemption_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint("code", name="uq_promo_codes_code"),
    )
    op.create_index(
        "ix_promo_codes_active",
        "promo_codes",
        ["is_active", "expires_at"],
    )

    op.create_table(
        "promo_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "promo_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("promo_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "redeemed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "promo_code_id",
            "user_id",
            name="uq_promo_redemptions_code_user",
        ),
    )
    op.create_index(
        "ix_promo_redemptions_promo_code_id",
        "promo_redemptions",
        ["promo_code_id"],
    )
    op.create_index(
        "ix_promo_redemptions_user_id",
        "promo_redemptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_promo_redemptions_user_id", table_name="promo_redemptions")
    op.drop_index(
        "ix_promo_redemptions_promo_code_id",
        table_name="promo_redemptions",
    )
    op.drop_table("promo_redemptions")
    op.drop_index("ix_promo_codes_active", table_name="promo_codes")
    op.drop_table("promo_codes")
