"""Payment card fingerprint storage for cross-account abuse review."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_card_fingerprints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("card_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stripe_event_id",
            name="uq_payment_card_fingerprints_stripe_event_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "card_fingerprint",
            name="uq_payment_card_fingerprints_user_card",
        ),
    )
    op.create_index(
        "ix_payment_card_fingerprints_user_id",
        "payment_card_fingerprints",
        ["user_id"],
    )
    op.create_index(
        "ix_payment_card_fingerprints_card_fingerprint",
        "payment_card_fingerprints",
        ["card_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_card_fingerprints_card_fingerprint",
        table_name="payment_card_fingerprints",
    )
    op.drop_index(
        "ix_payment_card_fingerprints_user_id",
        table_name="payment_card_fingerprints",
    )
    op.drop_table("payment_card_fingerprints")
