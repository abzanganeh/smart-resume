"""llm_configs: per-tier LLM routing table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-31

Implements Step 19 of ``docs/IMPLEMENTATION_PLAN.md`` (LLM Upgrade
Billing + Routing) and §18.9 of ``SYSTEM_DESIGN_PHASE_2.md``.

The orchestrator's Phase 3 middleware reads the active row for the
resolved tier (standard / better / best) instead of hard-coding model
strings.  Admin edits via Step 35 (§19.7) audit-write here under the
same effective_from / is_active pattern as ``plan_configs``.

Reuses the existing ``llm_upgrade_tier`` ENUM created by
``0002_billing`` and creates a new ``llm_config_provider`` ENUM
mirroring the literal in ``app/config.py``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


LLM_PROVIDER_ENUM = "llm_config_provider"


def upgrade() -> None:
    bind = op.get_bind()

    provider_enum = postgresql.ENUM(
        "openai",
        "anthropic",
        "gemini",
        "openrouter",
        "ollama",
        name=LLM_PROVIDER_ENUM,
        create_type=True,
    )
    provider_enum.create(bind, checkfirst=True)

    op.create_table(
        "llm_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tier",
            postgresql.ENUM(
                "standard",
                "better",
                "best",
                name="llm_upgrade_tier",
                create_type=False,
            ),
            nullable=False,
        ),
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
        sa.Column("model_string", sa.String(255), nullable=False),
        sa.Column(
            "phases_enabled",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_llm_configs_tier_active", "llm_configs", ["tier", "is_active"]
    )
    op.create_index(
        "uq_llm_configs_one_active_per_tier",
        "llm_configs",
        ["tier"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_llm_configs_one_active_per_tier", table_name="llm_configs"
    )
    op.drop_index("ix_llm_configs_tier_active", table_name="llm_configs")
    op.drop_table("llm_configs")
    bind = op.get_bind()
    postgresql.ENUM(name=LLM_PROVIDER_ENUM).drop(bind, checkfirst=True)
