"""Add signup IP and hashed device fingerprint columns to users."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("signup_ip", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("signup_device_fingerprint_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_users_signup_ip_created_at",
        "users",
        ["signup_ip", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_signup_ip_created_at", table_name="users")
    op.drop_column("users", "signup_device_fingerprint_hash")
    op.drop_column("users", "signup_ip")
