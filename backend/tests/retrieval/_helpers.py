"""Shared helpers for the retrieval test suite.

Builds canonical user + master-resume fixtures so each test focuses on
the specific behaviour it is asserting.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_resume import MasterResumeSectionType
from app.models.user import AuthProvider, User
from app.services.master_resume.chunking import Chunk
from app.services.master_resume.crud import (
    _insert_chunks,
    _upsert_master_resume,
)


async def create_test_user(
    db: AsyncSession, *, email: str = "ret-test@example.com"
) -> User:
    """Insert a minimal user row suitable for FK from master_resumes."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name="Ret Test",
        auth_provider=AuthProvider.email,
        password_hash="placeholder",  # not used in retrieval tests
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    return user


async def seed_master_resume_with_chunks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chunks: Iterable[Chunk],
    raw_text: str = "test raw text",
    parsed_sections: dict[str, Any] | None = None,
) -> None:
    """Create a ``MasterResume`` row + insert chunks (embeds via the fake)."""
    chunks = list(chunks)
    resume = await _upsert_master_resume(
        db,
        user_id=user_id,
        raw_text=raw_text,
        parsed_sections=parsed_sections or {},
    )
    await _insert_chunks(db, resume=resume, user_id=user_id, chunks=chunks)
    resume.chunk_count = len(chunks)
    await db.flush()
    await db.commit()


def chunk(
    section: str,
    content: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Chunk:
    """Build a :class:`Chunk` without hitting the chunker."""
    from app.services.master_resume.chunking import count_tokens

    return Chunk(
        section_type=MasterResumeSectionType(section),
        content=content,
        token_count=count_tokens(content),
        metadata=metadata or {},
    )
