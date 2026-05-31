"""phase_outputs_ext: ATS guidance fields on QAOutput (placeholder)

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-31

Implements Step 13 of ``docs/IMPLEMENTATION_PLAN.md``:

Extends Phase 4 ``QAOutput`` with ``ats_score``, ``blocking_issues``,
``score_ceiling``, and ``quick_wins``.  Session phase outputs are stored
in Redis today — no PostgreSQL JSONB column exists yet.  Persistent
``ResumeRecord`` storage (Step 27) will adopt the same schema shape.

This migration is intentionally a no-op placeholder so the Alembic
chain stays ordered before ``0005_cover_letter_fit``.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Phase outputs live in Redis; no DB schema change required yet.
    pass


def downgrade() -> None:
    pass
