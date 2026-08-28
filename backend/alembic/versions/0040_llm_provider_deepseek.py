"""Add deepseek to llm_config_provider enum for admin step pins."""

from __future__ import annotations

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_LLM_PROVIDER_ENUM = "llm_config_provider"


def upgrade() -> None:
    op.execute(
        f"ALTER TYPE {_LLM_PROVIDER_ENUM} ADD VALUE IF NOT EXISTS 'deepseek'"
    )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values safely; forward-only migration.
    pass
