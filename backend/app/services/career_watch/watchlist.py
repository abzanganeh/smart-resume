"""Career Watch watchlist CRUD."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.career_watch import (
    CareerAtsType,
    UserWatchedCompany,
    WatchedCompany,
)
from app.services.career_watch.detect import detect_ats_from_url
from app.services.career_watch.limits import assert_can_add_watch


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:200] or "company"


@dataclass(frozen=True, slots=True)
class WatchlistEntry:
    id: uuid.UUID
    watched_company_id: uuid.UUID
    company_name: str
    careers_page_url: str
    ats_type: CareerAtsType
    keywords: list[str]
    is_active: bool
    created_at: datetime


def _serialize(row: UserWatchedCompany) -> WatchlistEntry:
    company = row.watched_company
    return WatchlistEntry(
        id=row.id,
        watched_company_id=company.id,
        company_name=company.name,
        careers_page_url=company.careers_page_url,
        ats_type=company.ats_type,
        keywords=list(row.keywords or []),
        is_active=row.is_active,
        created_at=row.created_at,
    )


async def list_watchlist(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[WatchlistEntry]:
    stmt = (
        select(UserWatchedCompany)
        .where(UserWatchedCompany.user_id == user_id)
        .options(selectinload(UserWatchedCompany.watched_company))
        .order_by(UserWatchedCompany.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_serialize(row) for row in rows]


async def _get_or_create_company(
    session: AsyncSession,
    *,
    careers_page_url: str,
    company_name: str | None = None,
) -> WatchedCompany:
    detection = detect_ats_from_url(careers_page_url)
    slug_base = _slugify(company_name or detection.company_name or detection.board_token or "company")
    slug = slug_base
    suffix = 1
    while True:
        existing = (
            await session.execute(
                select(WatchedCompany).where(WatchedCompany.slug == slug)
            )
        ).scalar_one_or_none()
        if existing is None or existing.careers_page_url == detection.careers_page_url:
            break
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    if existing is not None:
        return existing

    company = WatchedCompany(
        id=uuid.uuid4(),
        name=company_name or detection.company_name or slug.replace("-", " ").title(),
        slug=slug,
        careers_page_url=detection.careers_page_url,
        ats_type=detection.ats_type,
        ats_board_token=detection.board_token,
    )
    session.add(company)
    await session.flush()
    return company


async def add_watch(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    careers_page_url: str,
    company_name: str | None = None,
    keywords: list[str] | None = None,
    user: Any | None = None,
) -> WatchlistEntry:
    from app.models.user import User

    if user is None:
        user = await session.get(User, user_id)
    if user is None:
        raise ValueError("user not found")
    await assert_can_add_watch(session, user=user)

    company = await _get_or_create_company(
        session,
        careers_page_url=careers_page_url,
        company_name=company_name,
    )
    existing = (
        await session.execute(
            select(UserWatchedCompany)
            .where(UserWatchedCompany.user_id == user_id)
            .where(UserWatchedCompany.watched_company_id == company.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.is_active = True
        if keywords is not None:
            existing.keywords = keywords
        await session.flush()
        await session.refresh(existing, attribute_names=["watched_company"])
        existing.watched_company = company
        return _serialize(existing)

    row = UserWatchedCompany(
        id=uuid.uuid4(),
        user_id=user_id,
        watched_company_id=company.id,
        keywords=keywords or [],
        is_active=True,
    )
    session.add(row)
    await session.flush()
    row.watched_company = company
    return _serialize(row)


async def update_watch_keywords(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    watch_id: uuid.UUID,
    keywords: list[str],
) -> WatchlistEntry:
    row = await _owned_watch(session, user_id=user_id, watch_id=watch_id)
    row.keywords = keywords
    await session.flush()
    return _serialize(row)


async def remove_watch(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    watch_id: uuid.UUID,
) -> None:
    row = await _owned_watch(session, user_id=user_id, watch_id=watch_id)
    row.is_active = False
    await session.flush()


async def _owned_watch(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    watch_id: uuid.UUID,
) -> UserWatchedCompany:
    stmt = (
        select(UserWatchedCompany)
        .where(UserWatchedCompany.id == watch_id)
        .where(UserWatchedCompany.user_id == user_id)
        .options(selectinload(UserWatchedCompany.watched_company))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise LookupError("watch not found")
    return row


async def detect_careers_page(careers_page_url: str) -> dict[str, str | None]:
    detection = detect_ats_from_url(careers_page_url)
    return {
        "ats_type": detection.ats_type.value,
        "board_token": detection.board_token,
        "careers_page_url": detection.careers_page_url,
        "company_name": detection.company_name,
    }


__all__ = [
    "WatchlistEntry",
    "add_watch",
    "detect_careers_page",
    "list_watchlist",
    "remove_watch",
    "update_watch_keywords",
]
