"""Job corpus global seed columns on watched_companies and job_cache

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "watched_companies",
        sa.Column(
            "is_global_seed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "watched_companies",
        sa.Column(
            "poll_priority_tier",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_watched_companies_global_seed_poll",
        "watched_companies",
        ["is_global_seed", "poll_priority_tier", "last_polled_at"],
    )

    op.add_column(
        "job_cache",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_cache",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_cache",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "job_cache",
        sa.Column("apply_url_normalized", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "job_cache",
        sa.Column("ats_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "job_cache",
        sa.Column("external_job_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_job_cache_active_first_seen",
        "job_cache",
        ["is_active", "first_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_cache_active_first_seen", table_name="job_cache")
    op.drop_column("job_cache", "external_job_id")
    op.drop_column("job_cache", "ats_type")
    op.drop_column("job_cache", "apply_url_normalized")
    op.drop_column("job_cache", "is_active")
    op.drop_column("job_cache", "last_seen_at")
    op.drop_column("job_cache", "first_seen_at")

    op.drop_index(
        "ix_watched_companies_global_seed_poll", table_name="watched_companies"
    )
    op.drop_column("watched_companies", "poll_priority_tier")
    op.drop_column("watched_companies", "is_global_seed")
