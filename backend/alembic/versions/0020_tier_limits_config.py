"""tier_limits_config: admin-configurable subscription tier limits

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-14

Pricing restructure milestone — seeds default limits for free, weekly,
Pro, Pro+, and Premium plan codes.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "tier_limits_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("resumes_per_period", sa.Integer(), nullable=False),
        sa.Column("cover_letters_per_period", sa.Integer(), nullable=False),
        sa.Column("searches_per_period", sa.Integer(), nullable=False),
        sa.Column("fit_analyses_per_period", sa.Integer(), nullable=False),
        sa.Column("checkups_per_period", sa.Integer(), nullable=True),
        sa.Column("story_sessions", sa.Integer(), nullable=True),
        sa.Column("coached_sessions", sa.Integer(), nullable=True),
        sa.Column("career_watch_companies", sa.Integer(), nullable=False),
        sa.Column("career_watch_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("tracker_active_limit", sa.Integer(), nullable=True),
        sa.Column(
            "whisper_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("whisper_uses_per_period", sa.Integer(), nullable=True),
        sa.Column("llm_provider", sa.String(64), nullable=False),
        sa.Column("llm_model_phase3", sa.String(255), nullable=False),
        sa.Column("soft_cap_message", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("updated_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        "ix_tier_limits_config_plan_code",
        "tier_limits_config",
        ["plan_code"],
    )
    op.create_index(
        "ix_tier_limits_config_plan_active",
        "tier_limits_config",
        ["plan_code", "is_active"],
    )

    # Seed default rows (import deferred so migration stays self-contained).
    from app.services.billing.tier_limits import get_seed_rows

    tier_limits = sa.table(
        "tier_limits_config",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("plan_code", sa.String),
        sa.column("resumes_per_period", sa.Integer),
        sa.column("cover_letters_per_period", sa.Integer),
        sa.column("searches_per_period", sa.Integer),
        sa.column("fit_analyses_per_period", sa.Integer),
        sa.column("checkups_per_period", sa.Integer),
        sa.column("story_sessions", sa.Integer),
        sa.column("coached_sessions", sa.Integer),
        sa.column("career_watch_companies", sa.Integer),
        sa.column("career_watch_interval_minutes", sa.Integer),
        sa.column("tracker_active_limit", sa.Integer),
        sa.column("whisper_enabled", sa.Boolean),
        sa.column("whisper_uses_per_period", sa.Integer),
        sa.column("llm_provider", sa.String),
        sa.column("llm_model_phase3", sa.String),
        sa.column("soft_cap_message", sa.Text),
        sa.column("is_active", sa.Boolean),
    )

    op.bulk_insert(
        tier_limits,
        [
            {
                "id": uuid.uuid4(),
                "is_active": True,
                **row,
            }
            for row in get_seed_rows()
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_tier_limits_config_plan_active", table_name="tier_limits_config")
    op.drop_index("ix_tier_limits_config_plan_code", table_name="tier_limits_config")
    op.drop_table("tier_limits_config")
