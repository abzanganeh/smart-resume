"""Add price_discount admin grant type for checkout offers."""

from __future__ import annotations

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_ADMIN_GRANT_TYPE_ENUM = "admin_grant_type"


def upgrade() -> None:
    op.execute(
        f"ALTER TYPE {_ADMIN_GRANT_TYPE_ENUM} "
        "ADD VALUE IF NOT EXISTS 'price_discount'"
    )


def downgrade() -> None:
    pass
