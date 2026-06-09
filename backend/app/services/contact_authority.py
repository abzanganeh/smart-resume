"""Authoritative contact merge — LLM must not override real user identity."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.models.rewrite import TailoredResumeOutput
from app.models.user import User
from app.models.userinfo import UserInfo

_PLACEHOLDER_NAMES = {"john doe", "jane doe", "candidate name", "your name", "full name", ""}
_PLACEHOLDER_EMAILS = {
    "john.doe@example.com",
    "jane.doe@example.com",
    "email@example.com",
    "youremail@example.com",
    "",
}
_PLACEHOLDER_PHONES = {"123-456-7890", "(123) 456-7890", "555-555-5555", ""}


def authoritative_contact(
    llm_contact: object,
    *,
    user_info: UserInfo | None = None,
    account_email: str | None = None,
) -> dict[str, Any]:
    """Merge LLM contact with session user_info and authenticated account data.

    Email priority: account (auth) > session user_info > LLM (non-placeholder only).
    The LLM sometimes invents plausible-looking emails (e.g. name@gmail.com) when
    the resume omits contact info — never trust those over the real account email.
    """
    c: dict[str, Any] = llm_contact if isinstance(llm_contact, dict) else {}
    result = dict(c)

    auth_email = (account_email or "").strip()
    info_email = (user_info.email if user_info else "") or ""
    info_email = info_email.strip()
    llm_email = (c.get("email") or "").strip()

    if auth_email:
        result["email"] = auth_email
    elif info_email:
        result["email"] = info_email
    elif llm_email.lower() not in _PLACEHOLDER_EMAILS:
        result["email"] = llm_email
    else:
        result["email"] = ""

    llm_name = (c.get("name") or "").strip()
    info_name = (user_info.name if user_info else "") or ""
    info_name = info_name.strip()
    # Honor a deliberate rename on the tailored resume (e.g. chat or inline edit).
    # When names match, profile and tailored agree — same as preferring user_info.
    if llm_name.lower() not in _PLACEHOLDER_NAMES and info_name and llm_name != info_name:
        result["name"] = llm_name
    elif info_name:
        result["name"] = info_name
    elif llm_name.lower() not in _PLACEHOLDER_NAMES:
        result["name"] = llm_name

    llm_phone = (c.get("phone") or "").strip()
    info_phone = (user_info.phone if user_info else None) or ""
    info_phone = str(info_phone).strip()
    if info_phone:
        result["phone"] = info_phone
    elif llm_phone in _PLACEHOLDER_PHONES:
        result["phone"] = ""

    if user_info:
        if not result.get("linkedin") and user_info.linkedin:
            result["linkedin"] = user_info.linkedin
        if not result.get("github") and user_info.github:
            result["github"] = user_info.github

    return result


def apply_authoritative_contact(
    output: TailoredResumeOutput,
    *,
    user_info: UserInfo | None = None,
    account_email: str | None = None,
) -> TailoredResumeOutput:
    """Return a copy of Phase 3 output with contact fields corrected."""
    merged = authoritative_contact(
        output.contact,
        user_info=user_info,
        account_email=account_email,
    )
    return output.model_copy(update={"contact": merged})


async def resolve_account_email(user_id: str | None) -> str | None:
    """Load the authenticated account email for contact authority."""
    if not user_id:
        return None
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    from app.db.engine import async_session_factory

    async with async_session_factory() as db:
        row = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if row is None:
            return None
        email = (row.email or "").strip()
        return email or None
