"""dashboard_tracker (first part): resume_records + ats_score_history

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-31

Implements Step 27 (first part) of ``docs/IMPLEMENTATION_PLAN.md`` and
``SYSTEM_DESIGN_PHASE_2.md`` §19.3.  Application tracker tables land in
a follow-up migration (Step 29).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

RESUME_RECORD_STATUS_ENUM = "resume_record_status"
ATS_RECALC_TYPE_ENUM = "ats_recalc_type"


def upgrade() -> None:
    bind = op.get_bind()

    resume_status = postgresql.ENUM(
        "draft",
        "applied",
        "interviewing",
        "offer",
        "rejected",
        "withdrawn",
        name=RESUME_RECORD_STATUS_ENUM,
        create_type=True,
    )
    recalc_type = postgresql.ENUM(
        "initial",
        "manual",
        "auto",
        name=ATS_RECALC_TYPE_ENUM,
        create_type=True,
    )
    resume_status.create(bind, checkfirst=True)
    recalc_type.create(bind, checkfirst=True)

    op.create_table(
        "resume_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("jd_title", sa.String(500), nullable=False),
        sa.Column("jd_company", sa.String(500), nullable=False),
        sa.Column("jd_text_hash", sa.String(64), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("current_ats_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("starting_ats_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "applied",
                "interviewing",
                "offer",
                "rejected",
                "withdrawn",
                name=RESUME_RECORD_STATUS_ENUM,
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_resume_records_user_id", "resume_records", ["user_id"])
    op.create_index(
        "ix_resume_records_user_updated",
        "resume_records",
        ["user_id", "updated_at"],
    )
    op.create_index(
        "uq_resume_records_user_jd_hash",
        "resume_records",
        ["user_id", "jd_text_hash"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "ats_score_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "resume_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resume_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column(
            "recalc_type",
            postgresql.ENUM(
                "initial",
                "manual",
                "auto",
                name=ATS_RECALC_TYPE_ENUM,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_ats_score_history_record_triggered",
        "ats_score_history",
        ["resume_record_id", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ats_score_history_record_triggered", table_name="ats_score_history")
    op.drop_table("ats_score_history")

    op.drop_index("uq_resume_records_user_jd_hash", table_name="resume_records")
    op.drop_index("ix_resume_records_user_updated", table_name="resume_records")
    op.drop_index("ix_resume_records_user_id", table_name="resume_records")
    op.drop_table("resume_records")

    bind = op.get_bind()
    postgresql.ENUM(name=ATS_RECALC_TYPE_ENUM).drop(bind, checkfirst=True)
    postgresql.ENUM(name=RESUME_RECORD_STATUS_ENUM).drop(bind, checkfirst=True)
