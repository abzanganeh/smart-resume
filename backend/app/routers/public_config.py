"""Public runtime config endpoints (IMPLEMENTATION_PLAN section 6 'Public Runtime Config').

Three GET endpoints, all cacheable:

- ``GET /api/feature-flags``  - public flags (excluding visibility=internal),
  evaluated server-side per IMPLEMENTATION_PLAN section 6 schema.
- ``GET /api/billing/prices``  - canonical public price list reflecting current PlanConfig.
  This route is partially handled in app.routers.billing already (the
  Step 7 implementation); we leave that intact and ONLY add the
  feature-flags + announcements pieces here.
- ``GET /api/announcements``  - active announcement banners filtered by audience.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.models.admin import (
    Announcement,
    AnnouncementAudience,
    FeatureFlag,
    FeatureFlagVisibility,
)
from app.models.billing import (
    Subscription,
    SubscriptionStatus,
)
from app.models.user import User
from app.services.billing.promo_offers import lookup_public_offer
from app.services.billing.public_prices import build_public_billing_prices

router = APIRouter(tags=["public-config"])

_FLAG_CACHE_HEADER = ("Cache-Control", "public, max-age=60")


def _hash_email_to_pct(email: str, key: str) -> int:
    """Stable bucketing 0-99 for ``(email, flag_key)``.

    SHA-256 mod 100 gives a uniform distribution and is deterministic
    across processes / restarts.
    """
    h = hashlib.sha256(f"{email}|{key}".encode("utf-8")).hexdigest()
    return int(h, 16) % 100


def _evaluate_flag(flag: FeatureFlag, user_email: str | None) -> bool:
    """Apply allowlist/blocklist + rollout to decide an enabled state."""
    email = (user_email or "").strip().lower()
    if email and email in (e.lower() for e in (flag.blocklist_emails or [])):
        return False
    if email and email in (e.lower() for e in (flag.allowlist_emails or [])):
        return True
    if not flag.enabled:
        return False
    if flag.rollout_percent >= 100:
        return True
    if flag.rollout_percent <= 0:
        return False
    return _hash_email_to_pct(email or "anon", flag.key) < flag.rollout_percent


@router.get("/api/feature-flags")
@limiter.limit("120/minute")
async def public_feature_flags(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User | None, Depends(lambda: None)] = None,  # placeholder
) -> dict[str, Any]:
    """Public flag list resolved against the current user (if any).

    Authentication is optional - anonymous callers get the rollout
    decision against a bucketing key of ``"anon"``.  Use the bearer
    token when available so allowlist / blocklist / rollout decisions
    match the user's view.
    """
    rows = list(
        (
            await db.execute(
                select(FeatureFlag).where(
                    FeatureFlag.visibility == FeatureFlagVisibility.public
                )
            )
        )
        .scalars()
        .all()
    )

    auth = request.headers.get("authorization", "")
    user_email: str | None = None
    if auth.lower().startswith("bearer "):
        try:
            from app.services.auth.tokens import decode_access_token
            claims = decode_access_token(auth[7:].strip(), expected_type="access")
            uid = claims.get("sub")
            if uid:
                from sqlalchemy import select as _select
                u = (
                    await db.execute(
                        _select(User.email).where(User.id == uid)
                    )
                ).scalar_one_or_none()
                if u:
                    user_email = u
        except Exception:
            user_email = None

    flags_payload: dict[str, Any] = {}
    latest = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for f in rows:
        flags_payload[f.key] = {
            "enabled": _evaluate_flag(f, user_email),
            "variant": f.variant,
        }
        if f.updated_at > latest:
            latest = f.updated_at
    response.headers["Cache-Control"] = _FLAG_CACHE_HEADER[1]
    return {
        "version": f"fflag-{latest.isoformat()}",
        "flags": flags_payload,
    }


@router.get("/api/announcements")
@limiter.limit("120/minute")
async def public_announcements(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Active announcements visible to the caller's audience."""
    now = datetime.now(timezone.utc)
    rows = list(
        (
            await db.execute(
                select(Announcement)
                .where(Announcement.starts_at <= now)
                .where(Announcement.ends_at >= now)
                .order_by(Announcement.starts_at.desc())
            )
        )
        .scalars()
        .all()
    )

    auth = request.headers.get("authorization", "")
    is_subscribed = False
    if auth.lower().startswith("bearer "):
        try:
            from app.services.auth.tokens import decode_access_token

            claims = decode_access_token(auth[7:].strip(), expected_type="access")
            uid = claims.get("sub")
            if uid:
                u = (
                    await db.execute(select(User).where(User.id == uid))
                ).scalar_one_or_none()
                if u:
                    sub = (
                        await db.execute(
                            select(Subscription)
                            .where(Subscription.user_id == u.id)
                            .where(
                                Subscription.status.in_(
                                    [
                                        SubscriptionStatus.active,
                                        SubscriptionStatus.trialing,
                                        SubscriptionStatus.grace,
                                        SubscriptionStatus.cancel_at_period_end,
                                    ]
                                )
                            )
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    is_subscribed = sub is not None
        except Exception:
            pass

    items = []
    latest = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for a in rows:
        if a.audience == AnnouncementAudience.admin:
            continue
        if a.audience == AnnouncementAudience.subscribed and not is_subscribed:
            continue
        items.append(
            {
                "id": str(a.id),
                "slug": a.slug,
                "title": a.title,
                "body_markdown": a.body_markdown,
                "severity": a.severity.value,
                "starts_at": a.starts_at.isoformat(),
                "ends_at": a.ends_at.isoformat(),
                "audience": a.audience.value,
                "cta_label": a.cta_label,
                "cta_url": a.cta_url,
            }
        )
        if a.updated_at > latest:
            latest = a.updated_at
    response.headers["Cache-Control"] = _FLAG_CACHE_HEADER[1]
    return {
        "version": f"ann-{latest.isoformat()}",
        "items": items,
    }


@router.get("/api/billing/prices")
@limiter.limit("120/minute")
async def public_billing_prices(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Canonical public price list (base plans only; LLM add-ons removed)."""
    payload = await build_public_billing_prices(db)
    response.headers["Cache-Control"] = _FLAG_CACHE_HEADER[1]
    return payload


@router.get("/api/billing/offers/{code}")
@limiter.limit("120/minute")
async def public_billing_offer(
    request: Request,
    code: str,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Public, read-only checkout offer metadata for server-enforced deadlines."""
    offer = await lookup_public_offer(db, code=code)
    if offer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "offer_not_found"},
        )
    response.headers["Cache-Control"] = "public, max-age=30"
    return offer.to_dict()


__all__ = ["router"]
