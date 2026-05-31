"""jobs step 23: saved_job bookmarks, hirebase artifact, job default filters

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "master_resumes",
        sa.Column("hirebase_artifact_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "job_default_filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_table(
        "saved_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_cache_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_cache.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_saved_job_user_id", "saved_job", ["user_id"])
    op.create_index("ix_saved_job_job_cache_id", "saved_job", ["job_cache_id"])
    op.create_index(
        "uq_saved_job_user_job",
        "saved_job",
        ["user_id", "job_cache_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_saved_job_user_job", table_name="saved_job")
    op.drop_index("ix_saved_job_job_cache_id", table_name="saved_job")
    op.drop_index("ix_saved_job_user_id", table_name="saved_job")
    op.drop_table("saved_job")
    op.drop_column("users", "job_default_filters")
    op.drop_column("master_resumes", "hirebase_artifact_id")
