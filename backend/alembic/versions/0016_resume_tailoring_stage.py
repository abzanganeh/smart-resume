"""resume_records: tailoring_stage + display_name

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-06

Shows in-progress tailoring sessions on the dashboard before Phase 4 completes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

TAILORING_STAGE_ENUM = "resume_tailoring_stage"


def upgrade() -> None:
    bind = op.get_bind()
    stage_enum = postgresql.ENUM(
        "in_progress",
        "polished",
        name=TAILORING_STAGE_ENUM,
        create_type=True,
    )
    stage_enum.create(bind, checkfirst=True)

    op.add_column(
        "resume_records",
        sa.Column(
            "tailoring_stage",
            postgresql.ENUM(
                "in_progress",
                "polished",
                name=TAILORING_STAGE_ENUM,
                create_type=False,
            ),
            nullable=False,
            server_default="in_progress",
        ),
    )
    op.add_column(
        "resume_records",
        sa.Column("display_name", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_records", "display_name")
    op.drop_column("resume_records", "tailoring_stage")
    bind = op.get_bind()
    postgresql.ENUM(name=TAILORING_STAGE_ENUM).drop(bind, checkfirst=True)
