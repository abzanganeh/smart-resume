"""Append-only enforcement on the ``admin_audit_log`` table.

Migration ``0013_admin`` installs:

1. ``REVOKE UPDATE, DELETE ON admin_audit_log FROM smart_resume_app_user``
   (skipped silently if that role does not exist - common in test DBs).
2. Two ``BEFORE UPDATE`` / ``BEFORE DELETE`` triggers that raise the
   custom error ``admin_audit_log is append-only``.

The tests below verify the trigger half (since the test DB usually
runs as ``postgres`` superuser and would bypass the GRANT/REVOKE
half).  Both UPDATE and DELETE attempts must be rejected with a
``DBAPIError``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin_auth.audit import write_admin_audit


@pytest.mark.asyncio
async def test_admin_audit_log_blocks_update(db_session: AsyncSession) -> None:
    row = await write_admin_audit(
        db_session,
        actor_admin_id=None,
        action="audit_test_action",
        target_kind="test_target",
        target_id="t-1",
        after={"hello": "world"},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "UPDATE admin_audit_log SET action = 'tampered' "
                "WHERE id = :id"
            ),
            {"id": row.id},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_admin_audit_log_blocks_delete(db_session: AsyncSession) -> None:
    row = await write_admin_audit(
        db_session,
        actor_admin_id=None,
        action="audit_test_action_delete",
        target_kind="test_target",
        target_id="t-2",
        after={"hello": "world"},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM admin_audit_log WHERE id = :id"),
            {"id": row.id},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_admin_audit_log_revoke_present(db_session: AsyncSession) -> None:
    """Smoke-check that the REVOKE statement was issued for the app role.

    This test only runs when the ``smart_resume_app_user`` role
    exists.  If it doesn't (common in test DBs), the test is skipped
    rather than failing.
    """
    role_exists = (
        await db_session.execute(
            text(
                "SELECT 1 FROM pg_roles WHERE rolname = 'smart_resume_app_user'"
            )
        )
    ).scalar()
    if not role_exists:
        pytest.skip("smart_resume_app_user role not provisioned in this DB")

    privs = (
        await db_session.execute(
            text(
                "SELECT privilege_type FROM information_schema.table_privileges "
                "WHERE grantee = 'smart_resume_app_user' "
                "AND table_name = 'admin_audit_log'"
            )
        )
    ).scalars().all()
    assert "UPDATE" not in privs
    assert "DELETE" not in privs
