"""cover_letter_fit: fit_analyses persistence table

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-31

Implements Step 17 of ``docs/IMPLEMENTATION_PLAN.md``:

- ``fit_analyses`` — persisted job-fit results keyed by user with
  ``jd_hash``, ``jd_text``, and ``result_json`` (JSONB).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "fit_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("jd_hash", sa.String(64), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_fit_analyses_user_id", "fit_analyses", ["user_id"])
    op.create_index("ix_fit_analyses_jd_hash", "fit_analyses", ["jd_hash"])
    op.create_index(
        "ix_fit_analyses_user_created",
        "fit_analyses",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_fit_analyses_user_created", table_name="fit_analyses")
    op.drop_index("ix_fit_analyses_jd_hash", table_name="fit_analyses")
    op.drop_index("ix_fit_analyses_user_id", table_name="fit_analyses")
    op.drop_table("fit_analyses")
