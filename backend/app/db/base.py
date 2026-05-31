from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy ORM models.

    All models must subclass this.  Alembic's env.py imports
    ``Base.metadata`` to auto-detect tables for migrations.
    """
