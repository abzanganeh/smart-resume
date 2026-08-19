"""Add per-user restriction to promo_codes

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "promo_codes",
        sa.Column(
            "restricted_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_promo_codes_restricted_user_id_users",
        "promo_codes",
        "users",
        ["restricted_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_promo_codes_restricted_user_id",
        "promo_codes",
        ["restricted_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_promo_codes_restricted_user_id", table_name="promo_codes")
    op.drop_constraint(
        "fk_promo_codes_restricted_user_id_users",
        "promo_codes",
        type_="foreignkey",
    )
    op.drop_column("promo_codes", "restricted_user_id")
