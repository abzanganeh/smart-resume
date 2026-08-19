"""Extend ``user_auth_provider`` for Microsoft, LinkedIn, and Apple SSO."""

from __future__ import annotations

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_ENUM = "user_auth_provider"
_NEW_VALUES = ("microsoft", "linkedin", "apple")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE {_ENUM} ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values safely; no-op downgrade.
    pass
