"""user_corpus_chunks: multi-source RAG corpus per user

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-06

Stores embedded text fragments beyond the structured master resume:
accepted bullet edits, tailored resume sections, user notes, and claimed
keywords.  All fragments share the same 1536-dim text-embedding-3-small
vector space as master_resume_chunks so a single ANN query can retrieve
from both tables.

Design notes:
- No FK to master_resumes — corpus chunks may originate from sources
  that have no associated master resume row (notes, keywords).
- session_id (nullable) links a corpus chunk back to the tailoring
  session that produced it, enabling per-session filtering and cleanup.
- deleted_at is a soft-delete tombstone consistent with master_resume_chunks.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

CORPUS_SOURCE_ENUM = "corpus_source"


def upgrade() -> None:
    bind = op.get_bind()
    source_enum = postgresql.ENUM(
        "master_resume",
        "tailored_resume",
        "bullet_fix",
        "user_note",
        "claimed_keyword",
        name=CORPUS_SOURCE_ENUM,
        create_type=True,
    )
    source_enum.create(bind, checkfirst=True)

    op.create_table(
        "user_corpus_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Nullable — corpus chunks from notes/keywords have no session.
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column(
            "corpus_source",
            postgresql.ENUM(
                "master_resume",
                "tailored_resume",
                "bullet_fix",
                "user_note",
                "claimed_keyword",
                name=CORPUS_SOURCE_ENUM,
                create_type=False,
            ),
            nullable=False,
        ),
        # Mirror of master_resume_chunks.section_type — nullable because
        # user_note / claimed_keyword chunks do not belong to a section.
        sa.Column("section_type", sa.String(64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        # ARRAY placeholder — upgraded to vector(1536) via ALTER below,
        # following the same pattern as 0003_master_resume.
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=True,
        ),
        # Free-form JSON for provenance: bullet_index, company, jd_hash, etc.
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Soft-delete so historical references in retrieval_meta stay valid.
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Upgrade embedding column from ARRAY placeholder to the real vector type,
    # matching the pattern in 0003_master_resume.  Table is empty at this point.
    op.execute(
        "ALTER TABLE user_corpus_chunks "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING NULL::vector(1536)"
    )

    # Index for retrieval: filter by user + source, then order by embedding.
    op.create_index(
        "ix_user_corpus_chunks_user_source_live",
        "user_corpus_chunks",
        ["user_id", "corpus_source"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Index for session-scoped cleanup (wipe tailored_resume chunks on re-run).
    op.create_index(
        "ix_user_corpus_chunks_session",
        "user_corpus_chunks",
        ["session_id"],
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )

    # pgvector IVFFlat index for ANN retrieval.  Built after table creation
    # using raw DDL because SA / alembic do not have a first-class pgvector
    # index type.  ``lists=100`` is the recommended default for up to 1M rows.
    op.execute(
        """
        CREATE INDEX ix_user_corpus_chunks_embedding
        ON user_corpus_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_corpus_chunks_embedding", table_name="user_corpus_chunks")
    op.drop_index("ix_user_corpus_chunks_session", table_name="user_corpus_chunks")
    op.drop_index("ix_user_corpus_chunks_user_source_live", table_name="user_corpus_chunks")
    op.drop_table("user_corpus_chunks")
    bind = op.get_bind()
    postgresql.ENUM(name=CORPUS_SOURCE_ENUM).drop(bind, checkfirst=True)
