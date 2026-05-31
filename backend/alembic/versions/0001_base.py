"""base: enable pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-05-30

This is the baseline migration.  It enables the pgvector extension so that
subsequent migrations can create vector columns and indexes.  No application
tables are created here — they are added in later numbered migrations as
each release-phase step is implemented.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentionally left as a no-op: dropping the vector extension would
    # destroy all vector columns in any database that has data.  Removing
    # the extension must be a deliberate, manual operational decision.
    pass
