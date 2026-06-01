"""Lambda entrypoint for the notification scheduler family.

EventBridge fires this Lambda with a ``schedule`` field in the event
payload that selects which workflow to run:

- ``dispatch_notifications`` — call
  :func:`dispatch_pending_notifications` to ship pending outbox rows
  to email / push / SMS / in-app channels (every 5 minutes).
- ``grace_tick`` — call :func:`run_grace_tick` to drive the §7.6
  state machine forward (24h reminders, 60h reminders, 72h expiry).
  Cron: every 15 minutes.
- ``stripe_price_sync`` — call :func:`run_stripe_price_sync` to
  detect drift between Stripe prices and ``PlanConfig`` rows.
  Cron: nightly (e.g. 03:00 UTC).

The handler is intentionally thin — all business logic lives in the
``app/services`` modules so the unit / integration tests can exercise
them without the Lambda runtime in the loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


_SUPPORTED_SCHEDULES = {
    "dispatch_notifications",
    "grace_tick",
    "stripe_price_sync",
}


def _resolve_schedule(event: dict[str, Any]) -> str:
    """Return the schedule label from the event payload."""
    detail = event.get("detail") or {}
    schedule = (
        detail.get("schedule")
        or event.get("schedule")
    )
    if schedule in _SUPPORTED_SCHEDULES:
        return str(schedule)
    # EventBridge rule-name fallback so a misformed payload still
    # routes deterministically when the rule name encodes the intent.
    resources = event.get("resources") or []
    for res in resources:
        for label in _SUPPORTED_SCHEDULES:
            if label in str(res):
                return label
    return "dispatch_notifications"


async def _run_dispatch() -> dict[str, Any]:
    """Wrapper that opens an async session and dispatches pending rows."""
    from app.db.engine import async_session_factory  # type: ignore[import-not-found]
    from app.services.notifications.scheduler import (  # type: ignore[import-not-found]
        dispatch_pending_notifications,
    )

    async with async_session_factory() as session:
        result = await dispatch_pending_notifications(session)
        await session.commit()
    return {
        "schedule": "dispatch_notifications",
        "inspected": result.inspected,
        "dispatched": result.dispatched,
        "failed": result.failed,
    }


async def _run_grace_tick() -> dict[str, Any]:
    from app.db.engine import async_session_factory  # type: ignore[import-not-found]
    from app.services.billing.grace_tick import run_grace_tick  # type: ignore[import-not-found]

    async with async_session_factory() as session:
        result = await run_grace_tick(session)
        await session.commit()
    return {
        "schedule": "grace_tick",
        "inspected": result.inspected,
        "expired": [str(s) for s in result.expired],
        "reminders_emitted": result.reminders_emitted,
    }


async def _run_price_sync() -> dict[str, Any]:
    from app.db.engine import async_session_factory  # type: ignore[import-not-found]
    from app.services.billing.price_sync import run_stripe_price_sync  # type: ignore[import-not-found]

    async with async_session_factory() as session:
        result = await run_stripe_price_sync(session)
        await session.commit()
    return {
        "schedule": "stripe_price_sync",
        "inspected": result.inspected,
        "drift_count": len(result.drifts),
        "drifts": [
            {"code": d.code, "kind": d.kind} for d in result.drifts
        ],
        "audit_ids": [str(a) for a in result.audit_ids],
    }


_DISPATCH_TABLE = {
    "dispatch_notifications": _run_dispatch,
    "grace_tick": _run_grace_tick,
    "stripe_price_sync": _run_price_sync,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge → Lambda entrypoint.  Delegates by schedule label."""
    schedule = _resolve_schedule(event)
    coro = _DISPATCH_TABLE[schedule]()
    result = asyncio.get_event_loop().run_until_complete(coro)
    log.info(
        "notification_scheduler.completed",
        extra={"schedule": schedule, "result": json.dumps(result, default=str)},
    )
    return result


__all__ = ["handler"]
