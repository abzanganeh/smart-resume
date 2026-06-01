"""export jobs and account closure requests

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-31

Implements Step 33–34 of ``docs/IMPLEMENTATION_PLAN.md`` and
``SYSTEM_DESIGN_PHASE_2.md`` §19.6.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

EXPORT_JOB_STATUS_ENUM = "export_job_status"


def upgrade() -> None:
    bind = op.get_bind()

    status = postgresql.ENUM(
        "pending",
        "processing",
        "ready",
        "failed",
        name=EXPORT_JOB_STATUS_ENUM,
        create_type=True,
    )
    status.create(bind, checkfirst=True)

    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name=EXPORT_JOB_STATUS_ENUM, create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("s3_key", sa.String(length=1024), nullable=True),
        sa.Column("presigned_url", sa.Text(), nullable=True),
        sa.Column("presigned_url_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"])
    op.create_index("ix_export_jobs_user_created", "export_jobs", ["user_id", "created_at"])

    op.create_table(
        "closure_requests",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("scheduled_delete_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("day23_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_closure_requests_scheduled_delete",
        "closure_requests",
        ["scheduled_delete_at"],
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_closure_requests_scheduled_delete", table_name="closure_requests")
    op.drop_table("closure_requests")
    op.drop_index("ix_export_jobs_user_created", table_name="export_jobs")
    op.drop_index("ix_export_jobs_user_id", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.execute(sa.text(f"DROP TYPE IF EXISTS {EXPORT_JOB_STATUS_ENUM}"))
