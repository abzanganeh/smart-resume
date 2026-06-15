"""jd_session_link: link a saved JD to its tailoring session

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-14

Adds ``session_id`` (nullable) to ``job_descriptions`` so the extension can
detect that a session already exists for a saved job and open the draft
instead of starting a new one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Column may already exist if create_all() ran before this migration.
    op.execute(
        "ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS session_id VARCHAR(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_descriptions_session_id "
        "ON job_descriptions (session_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_job_descriptions_session_id")
    op.execute("ALTER TABLE job_descriptions DROP COLUMN IF EXISTS session_id")
