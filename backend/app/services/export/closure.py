"""Account closure scheduling and execution (SYSTEM_DESIGN_PHASE_2 §19.6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.export import ClosureRequest, ExportJob
from app.models.notifications import NotificationChannel
from app.models.tracker import ApplicationAttachment
from app.models.user import User
from app.services.billing import subscription as sub_service
from app.services.export.storage import delete_user_export_prefix
from app.services.notifications.factory import build_notification
from app.services.tracker.s3 import delete_attachment

log = structlog.get_logger("export.closure")

GRACE_DAYS = settings.ACCOUNT_CLOSURE_GRACE_DAYS


@dataclass(frozen=True, slots=True)
class ClosureTickResult:
    inspected: int
    deleted: list[uuid.UUID]
    reminders_sent: int


async def schedule_closure(
    session: AsyncSession,
    *,
    user: User,
    cancel_subscription: bool = True,
) -> ClosureRequest:
    """Record closure request and mark user.closure_requested_at."""
    now = datetime.now(timezone.utc)
    scheduled = now + timedelta(days=GRACE_DAYS)

    existing = (
        await session.execute(
            select(ClosureRequest).where(
                ClosureRequest.user_id == user.id,
                ClosureRequest.cancelled_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if cancel_subscription:
        try:
            await sub_service.cancel_at_period_end(session, user=user)
        except ValueError:
            pass

    user.closure_requested_at = now
    row = ClosureRequest(
        user_id=user.id,
        requested_at=now,
        scheduled_delete_at=scheduled,
    )
    session.add(row)
    session.add(
        build_notification(
            user_id=user.id,
            type="account_closure_scheduled",
            channel=NotificationChannel.multi,
            category="account_closure",
            title="Account closure scheduled",
            body=f"Your account will be deleted on {scheduled.date().isoformat()}.",
            data={
                "scheduled_delete_at": scheduled.isoformat(),
                "url": "/settings/danger",
            },
        )
    )
    await session.flush()
    log.info(
        "closure.scheduled",
        user_id=str(user.id),
        scheduled_delete_at=scheduled.isoformat(),
    )
    return row


async def cancel_closure(session: AsyncSession, *, user: User) -> bool:
    """Cancel a pending closure and restore full access."""
    row = (
        await session.execute(
            select(ClosureRequest).where(
                ClosureRequest.user_id == user.id,
                ClosureRequest.cancelled_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None and user.closure_requested_at is None:
        return False

    now = datetime.now(timezone.utc)
    if row is not None:
        row.cancelled_at = now
    user.closure_requested_at = None
    await session.flush()
    log.info("closure.cancelled", user_id=str(user.id))
    return True


async def execute_closure(session: AsyncSession, *, user_id: uuid.UUID) -> bool:
    """Hard-delete user and related S3 objects. Idempotent if user already gone."""
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        return False

    email = user.email
    display = user.display_name or email

    from app.models.tracker import Application

    attachment_rows = (
        await session.execute(
            select(ApplicationAttachment)
            .join(Application, ApplicationAttachment.application_id == Application.id)
            .where(Application.user_id == user_id)
        )
    ).scalars().all()
    for att in attachment_rows:
        delete_attachment(att.s3_key)

    export_jobs = (
        await session.execute(
            select(ExportJob).where(ExportJob.user_id == user_id)
        )
    ).scalars().all()
    from app.services.export.storage import delete_export_object

    for job in export_jobs:
        if job.s3_key:
            delete_export_object(job.s3_key)
    delete_user_export_prefix(user_id)

    # Send deletion email before removing user row.
    try:
        from app.services.auth.email import send_account_deleted_email

        await send_account_deleted_email(to_email=email, display_name=display)
    except Exception as exc:  # noqa: BLE001
        log.warning("closure.deletion_email_failed", user_id=str(user_id), error=str(exc))

    await session.execute(delete(User).where(User.id == user_id))
    await session.flush()
    log.info("closure.executed", user_id=str(user_id))
    return True


async def run_closure_tick(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> ClosureTickResult:
    """Process due closures and day-23 reminders."""
    now_dt = now or datetime.now(timezone.utc)
    deleted: list[uuid.UUID] = []
    reminders_sent = 0

    # Day-23 reminders (7 days before deletion)
    reminder_cutoff = now_dt + timedelta(days=7)
    reminder_rows = (
        await session.execute(
            select(ClosureRequest, User)
            .join(User, ClosureRequest.user_id == User.id)
            .where(ClosureRequest.cancelled_at.is_(None))
            .where(ClosureRequest.scheduled_delete_at <= reminder_cutoff)
            .where(ClosureRequest.scheduled_delete_at > now_dt)
            .where(ClosureRequest.day23_reminder_sent_at.is_(None))
            .with_for_update(skip_locked=True)
        )
    ).all()
    for closure, user in reminder_rows:
        session.add(
            build_notification(
                user_id=user.id,
                type="account_closure_reminder",
                channel=NotificationChannel.multi,
                category="account_closure",
                title="7 days until account deletion",
                body=(
                    f"Your account will be permanently deleted on "
                    f"{closure.scheduled_delete_at.date().isoformat()}."
                ),
                data={
                    "scheduled_delete_at": closure.scheduled_delete_at.isoformat(),
                    "url": "/settings/danger",
                },
            )
        )
        closure.day23_reminder_sent_at = now_dt
        reminders_sent += 1

    due_rows = (
        await session.execute(
            select(ClosureRequest)
            .where(ClosureRequest.cancelled_at.is_(None))
            .where(ClosureRequest.scheduled_delete_at <= now_dt)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()

    for closure in due_rows:
        if await execute_closure(session, user_id=closure.user_id):
            deleted.append(closure.user_id)

    if deleted or reminders_sent:
        await session.flush()

    log.info(
        "closure.tick.completed",
        inspected=len(due_rows),
        deleted=len(deleted),
        reminders_sent=reminders_sent,
    )
    return ClosureTickResult(
        inspected=len(due_rows),
        deleted=deleted,
        reminders_sent=reminders_sent,
    )


__all__ = [
    "ClosureTickResult",
    "cancel_closure",
    "execute_closure",
    "run_closure_tick",
    "schedule_closure",
]
