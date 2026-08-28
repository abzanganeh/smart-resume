"""step_llm_configs: per-pipeline-step LLM routing pins."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

LLM_PROVIDER_ENUM = "llm_config_provider"


def upgrade() -> None:
    op.create_table(
        "step_llm_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column(
            "provider",
            postgresql.ENUM(
                "openai",
                "anthropic",
                "gemini",
                "openrouter",
                "ollama",
                name=LLM_PROVIDER_ENUM,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("model_string", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by_admin_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_step_llm_configs_step_active",
        "step_llm_configs",
        ["step", "is_active"],
    )
    op.create_index(
        "uq_step_llm_configs_one_active_per_step",
        "step_llm_configs",
        ["step"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_step_llm_configs_one_active_per_step", table_name="step_llm_configs"
    )
    op.drop_index("ix_step_llm_configs_step_active", table_name="step_llm_configs")
    op.drop_table("step_llm_configs")
