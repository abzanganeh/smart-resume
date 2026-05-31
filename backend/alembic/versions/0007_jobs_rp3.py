"""jobs_rp3: job_cache, job_search_log, saved_search tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-31

Implements Step 22 of ``docs/IMPLEMENTATION_PLAN.md`` and
``SYSTEM_DESIGN_PHASE_2.md`` §18.10 (Job Search data models).

Note: the migration plan originally reserved ``0006_jobs_rp3`` but
``0006_llm_configs`` (Step 19) landed first; this revision chains from
``0006``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

JOB_SEARCH_SOURCE_ENUM = "job_search_source"
ALERT_FREQUENCY_ENUM = "alert_frequency"


def upgrade() -> None:
    bind = op.get_bind()

    search_source = postgresql.ENUM(
        "cache",
        "hirebase",
        "apify",
        name=JOB_SEARCH_SOURCE_ENUM,
        create_type=True,
    )
    alert_frequency = postgresql.ENUM(
        "off",
        "daily",
        "weekly",
        name=ALERT_FREQUENCY_ENUM,
        create_type=True,
    )
    search_source.create(bind, checkfirst=True)
    alert_frequency.create(bind, checkfirst=True)

    op.create_table(
        "job_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "external_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(500), nullable=False),
        sa.Column("company_normalized", sa.String(500), nullable=False),
        sa.Column("location", sa.String(500), nullable=False, server_default=""),
        sa.Column("location_city", sa.String(200), nullable=True),
        sa.Column("location_country", sa.String(200), nullable=True),
        sa.Column(
            "remote",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("salary_min_usd", sa.Integer(), nullable=True),
        sa.Column("salary_max_usd", sa.Integer(), nullable=True),
        sa.Column("salary_currency_original", sa.String(10), nullable=True),
        sa.Column(
            "employment_type",
            sa.String(80),
            nullable=False,
            server_default="",
        ),
        sa.Column("posted_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("apply_url", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "cached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedup_key", sa.String(512), nullable=False),
    )
    op.create_index(
        "ix_job_cache_company_normalized",
        "job_cache",
        ["company_normalized"],
    )
    op.create_index(
        "uq_job_cache_dedup_key",
        "job_cache",
        ["dedup_key"],
        unique=True,
    )
    op.create_index(
        "ix_job_cache_expires_at_cleanup",
        "job_cache",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    op.create_table(
        "job_search_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "source",
            postgresql.ENUM(
                "cache",
                "hirebase",
                "apify",
                name=JOB_SEARCH_SOURCE_ENUM,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "cost_usd",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_job_search_log_user_id", "job_search_log", ["user_id"])
    op.create_index("ix_job_search_log_created_at", "job_search_log", ["created_at"])
    op.create_index(
        "ix_job_search_log_query_created",
        "job_search_log",
        ["query", "created_at"],
    )

    op.create_table(
        "saved_search",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "alert_frequency",
            postgresql.ENUM(
                "off",
                "daily",
                "weekly",
                name=ALERT_FREQUENCY_ENUM,
                create_type=False,
            ),
            nullable=False,
            server_default="off",
        ),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_saved_search_user_id", "saved_search", ["user_id"])
    op.create_index(
        "ix_saved_search_alert_frequency",
        "saved_search",
        ["alert_frequency"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_search_alert_frequency", table_name="saved_search")
    op.drop_index("ix_saved_search_user_id", table_name="saved_search")
    op.drop_table("saved_search")

    op.drop_index("ix_job_search_log_query_created", table_name="job_search_log")
    op.drop_index("ix_job_search_log_created_at", table_name="job_search_log")
    op.drop_index("ix_job_search_log_user_id", table_name="job_search_log")
    op.drop_table("job_search_log")

    op.drop_index("ix_job_cache_expires_at_cleanup", table_name="job_cache")
    op.drop_index("uq_job_cache_dedup_key", table_name="job_cache")
    op.drop_index("ix_job_cache_company_normalized", table_name="job_cache")
    op.drop_table("job_cache")

    bind = op.get_bind()
    postgresql.ENUM(name=ALERT_FREQUENCY_ENUM).drop(bind, checkfirst=True)
    postgresql.ENUM(name=JOB_SEARCH_SOURCE_ENUM).drop(bind, checkfirst=True)
