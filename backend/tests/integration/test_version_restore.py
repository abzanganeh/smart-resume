"""Version restore — regression for the 'still shows Restore after restoring' bug.

The restore endpoint used to hand back the *old* snapshot's own version number
instead of creating a new snapshot, so the frontend's "current version"
tracking (which always uses the highest version number in the list) fell out
of sync and the restored row never flipped its button state.
"""

from __future__ import annotations

import pytest

from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.routers.phases import _append_version_snapshot, restore_version
from app.services.session_store import create_session, get_session, update_session

pytestmark = pytest.mark.integration


async def test_restore_creates_new_version_instead_of_reusing_old_number() -> None:
    session = await create_session()

    v1 = _append_version_snapshot(
        session,
        label="User edit: experience/add/Sina Leasing",
        output=TailoredResumeOutput(
            experience=[TailoredExperienceEntry(company="Sina Leasing", bullets=["b1"])]
        ),
    )
    _append_version_snapshot(
        session,
        label="AI rewrite",
        output=TailoredResumeOutput(experience=[]),  # the bad regenerate that dropped it
    )
    session.phase3_output = session.phase3_versions[-1].output
    await update_session(session)

    result = await restore_version(session.session_id, v1.snapshot_id)

    reloaded = await get_session(session.session_id)
    assert reloaded is not None

    # A brand-new snapshot must be created — never the old snapshot's own number.
    assert result["version"] != v1.version
    assert result["version"] == max(v.version for v in reloaded.phase3_versions)
    assert len(reloaded.phase3_versions) == 3
    assert "Restored from v" in reloaded.phase3_versions[-1].label

    # Content is correctly restored either way.
    assert reloaded.phase3_output.experience[0].company == "Sina Leasing"
    assert result["tailored_output"]["experience"][0]["company"] == "Sina Leasing"


async def test_restore_missing_snapshot_returns_404() -> None:
    from fastapi import HTTPException

    session = await create_session()
    with pytest.raises(HTTPException) as exc_info:
        await restore_version(session.session_id, "does-not-exist")
    assert exc_info.value.status_code == 404
