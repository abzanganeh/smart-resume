"""Store Stripe card fingerprints and flag cross-account reuse for review."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import stripe
import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import PaymentCardFingerprint
from app.models.user import User

log = structlog.get_logger("billing.card_fingerprint")

CARD_FINGERPRINT_REVIEW_THRESHOLD = 3
CARD_FINGERPRINT_CLUSTER_FLAG = "card_fingerprint_cluster"


def extract_card_fingerprint(stripe_object: dict[str, Any]) -> str | None:
    """Read ``payment_method.card.fingerprint`` from an expanded webhook object."""
    payment_intent = stripe_object.get("payment_intent")
    if isinstance(payment_intent, dict):
        found = _fingerprint_from_payment_method(payment_intent.get("payment_method"))
        if found:
            return found

    charge = stripe_object.get("charge")
    if isinstance(charge, dict):
        details = charge.get("payment_method_details") or {}
        card = details.get("card") or {}
        fp = card.get("fingerprint")
        if isinstance(fp, str) and fp.strip():
            return fp.strip()

    return None


def _fingerprint_from_payment_method(payment_method: Any) -> str | None:
    if not isinstance(payment_method, dict):
        return None
    card = payment_method.get("card") or {}
    fp = card.get("fingerprint")
    if isinstance(fp, str) and fp.strip():
        return fp.strip()
    return None


async def _resolve_fingerprint_from_stripe(stripe_object: dict[str, Any]) -> str | None:
    inline = extract_card_fingerprint(stripe_object)
    if inline or not settings.STRIPE_SECRET_KEY:
        return inline

    stripe.api_key = settings.STRIPE_SECRET_KEY

    payment_intent_id = stripe_object.get("payment_intent")
    if isinstance(payment_intent_id, dict):
        payment_intent_id = payment_intent_id.get("id")
    if isinstance(payment_intent_id, str) and payment_intent_id:
        try:
            pi = await asyncio.to_thread(
                stripe.PaymentIntent.retrieve,
                payment_intent_id,
                expand=["payment_method"],
            )
            pi_dict = pi.to_dict_recursive() if hasattr(pi, "to_dict_recursive") else dict(pi)
            found = extract_card_fingerprint(pi_dict)
            if found:
                return found
        except stripe.StripeError as exc:
            log.warning(
                "billing.card_fingerprint.payment_intent_lookup_failed",
                payment_intent_id=payment_intent_id,
                error=str(exc),
            )

    charge_id = stripe_object.get("charge")
    if isinstance(charge_id, dict):
        charge_id = charge_id.get("id")
    if isinstance(charge_id, str) and charge_id:
        try:
            charge = await asyncio.to_thread(stripe.Charge.retrieve, charge_id)
            charge_dict = (
                charge.to_dict_recursive() if hasattr(charge, "to_dict_recursive") else dict(charge)
            )
            return extract_card_fingerprint({"charge": charge_dict})
        except stripe.StripeError as exc:
            log.warning(
                "billing.card_fingerprint.charge_lookup_failed",
                charge_id=charge_id,
                error=str(exc),
            )

    return None


async def _flag_cluster_if_needed(
    session: AsyncSession,
    *,
    card_fingerprint: str,
) -> None:
    count = int(
        (
            await session.execute(
                select(func.count(func.distinct(PaymentCardFingerprint.user_id))).where(
                    PaymentCardFingerprint.card_fingerprint == card_fingerprint
                )
            )
        ).scalar()
        or 0
    )
    if count < CARD_FINGERPRINT_REVIEW_THRESHOLD:
        return

    user_ids = (
        await session.execute(
            select(PaymentCardFingerprint.user_id)
            .where(PaymentCardFingerprint.card_fingerprint == card_fingerprint)
            .distinct()
        )
    ).scalars().all()

    flagged = 0
    for user_id in user_ids:
        user = await session.get(User, user_id)
        if user is None:
            continue
        if user.signup_abuse_review_flag is None:
            user.signup_abuse_review_flag = CARD_FINGERPRINT_CLUSTER_FLAG
            flagged += 1

    if flagged:
        await session.flush()
        log.info(
            "billing.card_fingerprint.cluster_flagged",
            card_fingerprint=card_fingerprint[:8] + "…",
            distinct_accounts=count,
            newly_flagged=flagged,
        )


async def record_payment_card_fingerprint(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    stripe_event_id: str,
    stripe_object: dict[str, Any],
) -> None:
    """Persist a card fingerprint from a successful payment webhook."""
    fingerprint = await _resolve_fingerprint_from_stripe(stripe_object)
    if not fingerprint:
        log.debug(
            "billing.card_fingerprint.unavailable",
            stripe_event_id=stripe_event_id,
            user_id=str(user_id),
        )
        return

    row = PaymentCardFingerprint(
        user_id=user_id,
        card_fingerprint=fingerprint,
        stripe_event_id=stripe_event_id,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        session.expunge(row)
        log.debug(
            "billing.card_fingerprint.duplicate_noop",
            stripe_event_id=stripe_event_id,
            user_id=str(user_id),
        )
        return

    await _flag_cluster_if_needed(session, card_fingerprint=fingerprint)


__all__ = [
    "CARD_FINGERPRINT_CLUSTER_FLAG",
    "CARD_FINGERPRINT_REVIEW_THRESHOLD",
    "extract_card_fingerprint",
    "record_payment_card_fingerprint",
]
