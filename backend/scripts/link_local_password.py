#!/usr/bin/env python3
"""Local dev only: attach an email/password to an existing SSO account.

Usage (from repo root):
  docker compose exec backend uv run python scripts/link_local_password.py EMAIL PASSWORD

Refused unless APP_ENV=development.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from app.db.engine import async_session_factory
from app.models.user import User
from app.services.auth.password import check_strength, hash_password


async def main(email: str, password: str) -> None:
    if os.environ.get("APP_ENV") != "development":
        print("Refused: APP_ENV must be development.", file=sys.stderr)
        sys.exit(1)

    email = email.lower().strip()
    check_strength(password, user_inputs=[email])

    async with async_session_factory() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"No user found for {email}", file=sys.stderr)
            sys.exit(1)
        if user.password_hash:
            print(f"{email} already has a password — use Sign in.", file=sys.stderr)
            sys.exit(1)

        user.password_hash = hash_password(password)
        await db.commit()
        print(f"Password set for {email} ({user.auth_provider.value} account).")
        print("You can now sign in with email + password on the Sign in tab.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: link_local_password.py EMAIL PASSWORD",
            file=sys.stderr,
        )
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
