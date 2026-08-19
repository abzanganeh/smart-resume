"""Add ``archived_at`` to ``applications`` for tracker active-slot enforcement.

Archiving marks a row as no longer counting against a user's
``tracker_active_limit`` without deleting the history.  ``archived_at IS
NULL`` means the row is active; a non-null timestamp means archived.

We also add a partial index on active rows (``archived_at IS NULL``) so
the active-count query used to enforce the per-plan cap stays cheap for
users with lots of history.

.. warning::
    ``downgrade()`` is **data-destructive**: dropping the ``archived_at``
    column permanently loses the archive timestamps.  Rolling back after
    any archiving activity in production means the tracker cannot tell
    archived rows from active ones and will re-count them against the
    active limit.  If a rollback in a live environment is ever needed,
    dump ``(id, archived_at)`` for non-null rows first — see
    ``docs/RUNBOOK-migrations.md`` for the procedure.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_applications_user_active",
        "applications",
        ["user_id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_applications_user_active", table_name="applications")
    op.drop_column("applications", "archived_at")
