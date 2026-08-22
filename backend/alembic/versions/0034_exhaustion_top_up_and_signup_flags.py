"""Add exhaustion top-up action and signup abuse review flag."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_CREDIT_ACTION_ENUM = "credit_transaction_action"


def upgrade() -> None:
    op.execute(
        f"ALTER TYPE {_CREDIT_ACTION_ENUM} "
        "ADD VALUE IF NOT EXISTS 'exhaustion_top_up'"
    )
    op.add_column(
        "users",
        sa.Column("signup_abuse_review_flag", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "signup_abuse_review_flag")
