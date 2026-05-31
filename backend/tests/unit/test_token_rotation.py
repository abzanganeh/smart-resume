"""Refresh-token rotation + reuse-detection contract.

These tests are the security keystone for §18.2 / §8.2: presenting an
already-revoked refresh token must (1) raise
``RefreshTokenReuseError`` and (2) revoke *every* still-active token
for the affected user.

The tests are marked ``integration`` because they run against a real
Postgres database (the model uses Postgres-only ENUM + JSONB types).
They are placed under ``tests/unit/`` per the implementation plan.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, RefreshToken, User, UserTier
from app.services.auth.exceptions import (
    RefreshTokenReuseError,
    TokenInvalidError,
)
from app.services.auth.tokens import (
    create_refresh_token,
    hash_refresh_token,
    rotate_refresh_token,
)


pytestmark = pytest.mark.integration


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name="Test User",
        auth_provider=AuthProvider.email,
        password_hash="$2b$12$placeholder.placeholder.placeholder.placeholder.placeholder",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    return user


async def test_rotate_happy_path_revokes_old_and_issues_new(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, "alice@example.com")
    first = await create_refresh_token(
        db_session, user_id=user.id, device_fingerprint="fp-1"
    )

    second = await rotate_refresh_token(
        db_session,
        token=first.token,
        device_fingerprint="fp-1",
    )

    assert second.token != first.token
    assert second.row.parent_id == first.row.id

    # The first row is now revoked; the second is active.
    await db_session.refresh(first.row)
    assert first.row.revoked_at is not None
    assert second.row.revoked_at is None


async def test_rotate_unknown_token_raises_invalid(db_session: AsyncSession) -> None:
    with pytest.raises(TokenInvalidError):
        await rotate_refresh_token(
            db_session,
            token="nope-no-such-token",
            device_fingerprint="fp-1",
        )


async def test_replay_of_revoked_token_revokes_full_chain(
    db_session: AsyncSession,
) -> None:
    """The keystone reuse-detection test.

    Setup:
      - Issue token A.
      - Rotate A → B (A is now revoked).
      - Rotate B → C (B is now revoked, C is active).
      - Independently issue token D for the same user (e.g. a parallel
        device).  D is active and NOT part of the A/B/C chain.

    Action:
      - Replay token A (already revoked).

    Expected:
      - ``RefreshTokenReuseError`` is raised.
      - Every still-active row for that user is revoked, including D.
      - Other users are untouched.
    """
    user = await _make_user(db_session, "alice@example.com")
    other = await _make_user(db_session, "bob@example.com")

    a = await create_refresh_token(db_session, user_id=user.id, device_fingerprint="fp")
    b = await rotate_refresh_token(db_session, token=a.token, device_fingerprint="fp")
    c = await rotate_refresh_token(db_session, token=b.token, device_fingerprint="fp")

    # Parallel device — issued outside the A/B/C chain.
    d = await create_refresh_token(
        db_session, user_id=user.id, device_fingerprint="fp-2"
    )

    # Other user's token must survive the chain revocation.
    e = await create_refresh_token(
        db_session, user_id=other.id, device_fingerprint="fp-3"
    )

    # Sanity: before replay, C, D, and E are active; A and B are revoked.
    assert c.row.revoked_at is None
    assert d.row.revoked_at is None
    assert e.row.revoked_at is None

    with pytest.raises(RefreshTokenReuseError) as excinfo:
        await rotate_refresh_token(db_session, token=a.token, device_fingerprint="fp")
    assert excinfo.value.user_id == str(user.id)

    # Reload all tokens — A and B already revoked; C and D must now be revoked too.
    rows = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()
    assert len(rows) == 4
    for row in rows:
        assert row.revoked_at is not None, (
            f"token {row.id} should have been revoked by reuse detection"
        )

    # Other user is untouched.
    await db_session.refresh(e.row)
    assert e.row.revoked_at is None


async def test_token_hash_is_sha256_hex(db_session: AsyncSession) -> None:
    """Storage is hashed, never plaintext."""
    user = await _make_user(db_session, "alice@example.com")
    issued = await create_refresh_token(
        db_session, user_id=user.id, device_fingerprint="fp"
    )
    assert issued.row.token_hash == hash_refresh_token(issued.token)
    assert len(issued.row.token_hash) == 64
    assert int(issued.row.token_hash, 16) >= 0  # valid hex
