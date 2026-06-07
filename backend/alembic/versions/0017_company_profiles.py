"""company_profiles: cache company intelligence extracted from JD text

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-06

Each row caches the mission, values, and culture signals extracted from a
company's job description.  The cache key is a normalised slug of the
company name so all JDs from the same employer share one row.  TTL
enforcement is done at read time in the service layer, not by a DB job.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Normalised slug, e.g. "google", "amazon", "stripe".
        # Unique so we can upsert by company_key without duplicates.
        sa.Column("company_key", sa.String(200), nullable=False),
        sa.Column("company_name", sa.String(500), nullable=False),
        # Extracted fields — TEXT so there is no length cap.
        sa.Column("mission", sa.Text(), nullable=False, server_default=""),
        sa.Column("values", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("culture_notes", sa.Text(), nullable=False, server_default=""),
        # Timestamp of last extraction so the service can enforce TTL.
        sa.Column(
            "cached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # A unique index serves both uniqueness enforcement and fast lookups.
    # Do NOT add a UniqueConstraint on the same column — Postgres would create
    # two separate unique indexes, wasting space and breaking the downgrade path.
    op.create_index(
        "ix_company_profiles_company_key",
        "company_profiles",
        ["company_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_company_profiles_company_key", table_name="company_profiles")
    op.drop_table("company_profiles")
