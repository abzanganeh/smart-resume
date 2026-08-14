"""Career Watch tables — watched companies, job cache, alerts

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

CAREER_ATS_TYPE_ENUM = "career_ats_type"
CAREER_ALERT_STATUS_ENUM = "career_alert_status"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"CREATE TYPE {CAREER_ATS_TYPE_ENUM} AS ENUM ("
            "'unknown', 'greenhouse', 'lever', 'ashby', 'workday', 'generic_html'"
            ")"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TYPE {CAREER_ALERT_STATUS_ENUM} AS ENUM ("
            "'pending', 'sent', 'dismissed', 'expired'"
            ")"
        )
    )

    op.create_table(
        "watched_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("careers_page_url", sa.Text(), nullable=False),
        sa.Column(
            "ats_type",
            postgresql.ENUM(
                "unknown",
                "greenhouse",
                "lever",
                "ashby",
                "workday",
                "generic_html",
                name=CAREER_ATS_TYPE_ENUM,
                create_type=False,
            ),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("ats_board_token", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "poll_fail_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
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
        sa.UniqueConstraint("slug", name="uq_watched_companies_slug"),
    )
    op.create_index(
        "ix_watched_companies_active_poll",
        "watched_companies",
        ["is_active", "last_polled_at"],
    )

    op.create_table(
        "user_watched_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "watched_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watched_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "keywords",
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
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id", "watched_company_id", name="uq_user_watched_company"
        ),
    )
    op.create_index(
        "ix_user_watched_companies_user_id", "user_watched_companies", ["user_id"]
    )
    op.create_index(
        "ix_user_watched_companies_watched_company_id",
        "user_watched_companies",
        ["watched_company_id"],
    )
    op.create_index(
        "ix_user_watched_companies_active",
        "user_watched_companies",
        ["user_id", "is_active"],
    )

    op.create_table(
        "career_job_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "watched_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watched_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_job_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column(
            "location",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "apply_url",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "description_text",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "description_hash",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint(
            "watched_company_id",
            "external_job_id",
            name="uq_career_job_cache_company_external",
        ),
    )
    op.create_index(
        "ix_career_job_cache_watched_company_id",
        "career_job_cache",
        ["watched_company_id"],
    )
    op.create_index(
        "ix_career_job_cache_company_open",
        "career_job_cache",
        ["watched_company_id", "is_open"],
    )

    op.create_table(
        "career_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_watched_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_watched_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "career_job_cache_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("career_job_cache.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "sent",
                "dismissed",
                "expired",
                name=CAREER_ALERT_STATUS_ENUM,
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id", "career_job_cache_id", name="uq_career_alert_user_job"
        ),
    )
    op.create_index("ix_career_alerts_user_id", "career_alerts", ["user_id"])
    op.create_index(
        "ix_career_alerts_user_watched_company_id",
        "career_alerts",
        ["user_watched_company_id"],
    )
    op.create_index(
        "ix_career_alerts_career_job_cache_id",
        "career_alerts",
        ["career_job_cache_id"],
    )
    op.create_index(
        "ix_career_alerts_user_status",
        "career_alerts",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("career_alerts")
    op.drop_table("career_job_cache")
    op.drop_table("user_watched_companies")
    op.drop_table("watched_companies")
    op.execute(sa.text(f"DROP TYPE IF EXISTS {CAREER_ALERT_STATUS_ENUM}"))
    op.execute(sa.text(f"DROP TYPE IF EXISTS {CAREER_ATS_TYPE_ENUM}"))
