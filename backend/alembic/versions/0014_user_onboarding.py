"""user onboarding: ai choice + completion timestamp

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-03

Tracks whether a user has completed first-run onboarding (AI choice step)
and which AI mode they prefer (platform vs BYOK).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("onboarding_ai_choice", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_ai_choice")
    op.drop_column("users", "onboarding_completed_at")
