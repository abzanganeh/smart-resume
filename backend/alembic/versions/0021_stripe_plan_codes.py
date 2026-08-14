"""Deactivate legacy daily/monthly PlanConfig rows for pricing restructure.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-14

Slice 3 (stripe-plan-codes): drop daily plan; monthly/monthly_yearly
replaced by Pro / Pro+ / Premium codes seeded via bootstrap or admin.
"""

from __future__ import annotations

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE plan_configs
        SET is_active = false,
            effective_to = COALESCE(effective_to, now())
        WHERE code IN ('daily', 'monthly', 'monthly_yearly')
          AND is_active = true
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE plan_configs
        SET is_active = true,
            effective_to = NULL
        WHERE code IN ('daily', 'monthly', 'monthly_yearly')
        """
    )
