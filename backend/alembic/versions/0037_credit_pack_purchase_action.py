"""Add credit_pack_purchase ledger action for free-credit pack purchases."""

from __future__ import annotations

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_CREDIT_ACTION_ENUM = "credit_transaction_action"


def upgrade() -> None:
    op.execute(
        f"ALTER TYPE {_CREDIT_ACTION_ENUM} "
        "ADD VALUE IF NOT EXISTS 'credit_pack_purchase'"
    )


def downgrade() -> None:
    pass
