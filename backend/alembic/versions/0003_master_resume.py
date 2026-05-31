"""master_resume: profile document tables + pgvector ivfflat index

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-31

Implements Step 8 of ``docs/IMPLEMENTATION_PLAN.md``:

- ``master_resume_section_type`` ENUM (12 values) mirroring
  SYSTEM_DESIGN_PHASE_2 §18.4 storage block.
- ``master_resumes`` — one row per user (unique ``user_id``) with the
  raw upload, structured ``parsed_sections``, ``chunk_count``, and
  ``last_embedded_at`` bookkeeping.
- ``master_resume_chunks`` — one row per logical "available content"
  unit with ``token_count`` (tiktoken) and a 1536-dim ``pgvector``
  embedding produced by ``text-embedding-3-small``.
- ``ivfflat`` cosine index on ``master_resume_chunks.embedding`` with
  ``lists = 100`` per the implementation plan.
- Soft-delete tombstone (``deleted_at``) on chunks so version-snapshot
  transparency stays intact for older tailored resumes.

The ``vector`` extension is already enabled by ``0001_base``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


SECTION_TYPE_ENUM = "master_resume_section_type"
EMBEDDING_DIM = 1536


def upgrade() -> None:
    bind = op.get_bind()

    # -------------------------------------------------------------------
    # ENUM type
    # -------------------------------------------------------------------
    section_type = postgresql.ENUM(
        "summary",
        "experience",
        "skills",
        "education",
        "project",
        "cert",
        "publication",
        "award",
        "volunteer",
        "language",
        "patent",
        "other",
        name=SECTION_TYPE_ENUM,
        create_type=True,
    )
    section_type.create(bind, checkfirst=True)

    # -------------------------------------------------------------------
    # master_resumes
    # -------------------------------------------------------------------
    op.create_table(
        "master_resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "parsed_sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "chunk_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "last_embedded_at", sa.DateTime(timezone=True), nullable=True
        ),
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
        sa.UniqueConstraint("user_id", name="uq_master_resumes_user_id"),
    )
    op.create_index(
        "ix_master_resumes_user_id",
        "master_resumes",
        ["user_id"],
        unique=True,
    )

    # -------------------------------------------------------------------
    # master_resume_chunks
    # -------------------------------------------------------------------
    op.create_table(
        "master_resume_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "master_resume_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("master_resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_type",
            postgresql.ENUM(name=SECTION_TYPE_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "token_count", sa.Integer(), nullable=False, server_default="0"
        ),
        # The ``vector(N)`` column type is provided by the pgvector
        # extension that ``0001_base`` already enabled.  Inline SQL is the
        # most portable path — using ``pgvector.sqlalchemy.Vector`` here
        # also works but pulls the Python package into ``alembic/env.py``
        # at offline-migration generation time.
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()).with_variant(
            sa.Text(), "sqlite"
        ), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
    # Swap the placeholder ARRAY column for the real ``vector(N)`` type.
    # ``USING NULL::vector(N)`` is safe because the table is empty at
    # migration time.  Keeping it as a separate ALTER avoids relying on
    # SQLAlchemy's variant resolution for the production dialect.
    op.execute(
        f"ALTER TABLE master_resume_chunks "
        f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) "
        f"USING NULL::vector({EMBEDDING_DIM})"
    )

    op.create_index(
        "ix_master_resume_chunks_master_resume_id",
        "master_resume_chunks",
        ["master_resume_id"],
    )
    op.create_index(
        "ix_master_resume_chunks_user_id",
        "master_resume_chunks",
        ["user_id"],
    )
    op.create_index(
        "ix_master_resume_chunks_user_section_live",
        "master_resume_chunks",
        ["user_id", "section_type"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_master_resume_chunks_master_resume_id_created",
        "master_resume_chunks",
        ["master_resume_id", "created_at"],
    )

    # -------------------------------------------------------------------
    # pgvector ivfflat ANN index (IMPLEMENTATION_PLAN §5 + Step 8).
    #
    # ``lists = 100`` is the recommended starting point for small/medium
    # corpora; revisit at scale per the §5 "pgvector Index Strategy" note.
    # The index is built on the cosine operator family so the runtime
    # query uses ``ORDER BY embedding <=> :jd_vec`` (cosine distance).
    # -------------------------------------------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_master_resume_chunks_embedding_cos "
        "ON master_resume_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_master_resume_chunks_embedding_cos")
    op.drop_index(
        "ix_master_resume_chunks_master_resume_id_created",
        table_name="master_resume_chunks",
    )
    op.drop_index(
        "ix_master_resume_chunks_user_section_live",
        table_name="master_resume_chunks",
    )
    op.drop_index(
        "ix_master_resume_chunks_user_id",
        table_name="master_resume_chunks",
    )
    op.drop_index(
        "ix_master_resume_chunks_master_resume_id",
        table_name="master_resume_chunks",
    )
    op.drop_table("master_resume_chunks")

    op.drop_index("ix_master_resumes_user_id", table_name="master_resumes")
    op.drop_table("master_resumes")

    bind = op.get_bind()
    postgresql.ENUM(name=SECTION_TYPE_ENUM).drop(bind, checkfirst=True)
