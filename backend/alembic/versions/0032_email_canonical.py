"""Add ``users.email_canonical`` with a unique index for alias-safe signup."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.services.auth.email_canonical import canonicalize_email


revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_canonical", sa.String(320), nullable=True),
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, email, created_at FROM users ORDER BY created_at ASC"
        )
    ).fetchall()

    seen: dict[str, object] = {}
    for row in rows:
        canonical = canonicalize_email(row.email)
        owner = seen.get(canonical)
        if owner is None:
            email_canonical = canonical
            seen[canonical] = row.id
        else:
            # Oldest account owns the canonical identity; later aliases keep
            # their literal lowercased address so the unique index can build.
            email_canonical = row.email.strip().lower()
        conn.execute(
            sa.text(
                "UPDATE users SET email_canonical = :email_canonical WHERE id = :id"
            ),
            {"email_canonical": email_canonical, "id": row.id},
        )

    op.alter_column("users", "email_canonical", nullable=False)
    op.create_index(
        "uq_users_email_canonical",
        "users",
        ["email_canonical"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_canonical", table_name="users")
    op.drop_column("users", "email_canonical")
