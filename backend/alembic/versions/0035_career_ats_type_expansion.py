"""Expand career_ats_type enum for M19 ATS adapters."""

from __future__ import annotations

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_CAREER_ATS_TYPE_ENUM = "career_ats_type"
_NEW_VALUES = (
    "smartrecruiters",
    "workable",
    "recruitee",
    "breezy",
    "personio",
    "bamboohr",
)


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(
            f"ALTER TYPE {_CAREER_ATS_TYPE_ENUM} ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values safely; forward-only migration.
    pass
