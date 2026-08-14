"""Add fit_analyses_used counter to subscriptions for tier limit enforcement.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "fit_analyses_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "fit_analyses_used")
