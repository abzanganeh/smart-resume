"""Drop BYOK columns from users; migrate onboarding choice to platform.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET onboarding_ai_choice = 'platform' "
        "WHERE onboarding_ai_choice = 'byok'"
    )
    op.drop_column("users", "byok_api_key")
    op.drop_column("users", "byok_provider")
    op.drop_column("users", "byok_key_fingerprint")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("byok_api_key", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("byok_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("byok_key_fingerprint", sa.String(length=64), nullable=True),
    )
