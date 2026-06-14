"""job_descriptions: durable JD store for extension (Strategy B Phase 2)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-05

Adds the ``job_descriptions`` table. Extension-saved JDs are persisted here
so Open-in-Flint works without an in-progress tailoring session.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "job_descriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("company", sa.String(512), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="extension"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_job_descriptions_user_id", "job_descriptions", ["user_id"])
    op.create_index(
        "ix_job_descriptions_user_created",
        "job_descriptions",
        ["user_id", sa.text("created_at DESC")],
    )

    # Row-level security policy is declared up front so the table is ready
    # for Phase 3 (Supabase). At Phase 2 the application does NOT inject
    # ``app.current_user_id`` per request — see app/db/engine.py — so the
    # policy currently filters every row out for any direct connection.
    # Authorisation is enforced at the route layer instead: the
    # ``POST /api/job-descriptions`` handler restricts writes to the JWT's
    # user_id, and reads happen only via the ``flint:`` handoff token (a
    # capability) so the route never queries job_descriptions back. When
    # Phase 3 wires Supabase JWT claims to ``set_config('app.current_user_id', …)``
    # in middleware, this policy becomes the second line of defence
    # without any change here.
    op.execute("ALTER TABLE job_descriptions ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY job_descriptions_user_isolation
        ON job_descriptions
        USING (user_id = (current_setting('app.current_user_id', true))::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS job_descriptions_user_isolation ON job_descriptions")
    op.execute("ALTER TABLE job_descriptions DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_job_descriptions_user_created", table_name="job_descriptions")
    op.drop_index("ix_job_descriptions_user_id", table_name="job_descriptions")
    op.drop_table("job_descriptions")
