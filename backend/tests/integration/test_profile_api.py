"""End-to-end profile API: upload → list chunks → patch one chunk.

Asserts:

- ``POST /api/profile/resume`` (text body) creates a ``MasterResume``
  row and a set of ``MasterResumeChunk`` rows (one per logical bullet
  per SYSTEM_DESIGN_PHASE_2 §18.4).
- ``GET /api/profile/resume/chunks`` returns every live chunk.
- ``PATCH /api/profile/resume/chunks/{id}`` re-embeds **only** the
  edited chunk — other chunks' embeddings stay byte-identical so the
  retrieval surface is not invalidated unnecessarily.
- ``DELETE /api/profile/resume/chunks/{id}`` soft-deletes the row.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_resume import MasterResume, MasterResumeChunk
from app.routers.auth import REFRESH_COOKIE_NAME  # noqa: F401 — kept for parity
from app.services.master_resume.embedding import set_fake_embedder
from tests.retrieval.fake_embedder import deterministic_embed

pytestmark = pytest.mark.integration


REGISTER_PAYLOAD = {
    "email": "profile-user@example.com",
    "password": "tr0ub4dor&3sandwich-eats-paint",
    "display_name": "Profile User",
    "accepted_tos_version": "2026-06",
    "marketing_opt_in": False,
}


@pytest.fixture(autouse=True)
def _install_fake_embedder():
    """Keep embeddings deterministic (and offline) for the API suite."""
    set_fake_embedder(deterministic_embed)
    try:
        yield
    finally:
        set_fake_embedder(None)


async def _register_and_login(client: AsyncClient) -> str:
    """Return a valid access token."""
    r = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


SAMPLE_TEXT = (
    "John Doe — Senior Backend Engineer\n\n"
    "Summary: 8 years of Python, FastAPI, PostgreSQL, Kubernetes.\n\n"
    "Experience:\n"
    "- Built async pipelines at Acme for invoice processing in Python.\n"
    "- Migrated legacy Django monolith to FastAPI microservices.\n\n"
    "Skills:\n"
    "- Python, FastAPI, PostgreSQL, pgvector, Kubernetes, Redis\n\n"
    "Education:\n"
    "- BS Computer Science, MIT (2017)\n"
)


async def test_upload_list_patch_delete_roundtrip(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_login(app_client)
    headers = {"Authorization": f"Bearer {access}"}

    # --- POST /api/profile/resume (text body, no LLM) ---
    # Posting with no provider header means ``_structure_with_llm``
    # falls back to ``{}`` and the chunker uses the raw-text path —
    # exactly what we want for the offline test.
    r = await app_client.post(
        "/api/profile/resume",
        headers=headers,
        data={"text": SAMPLE_TEXT},
    )
    assert r.status_code == 201, r.text
    create_body = r.json()
    assert create_body["chunk_count"] >= 1
    assert create_body["last_embedded_at"] is not None
    chunks = create_body["chunks"]
    assert chunks, "POST must return the freshly-embedded chunks"

    # --- GET /api/profile/resume ---
    r = await app_client.get("/api/profile/resume", headers=headers)
    assert r.status_code == 200, r.text
    fetched = r.json()
    assert fetched["raw_text"].startswith("John Doe")
    assert fetched["chunk_count"] == create_body["chunk_count"]

    # --- GET /api/profile/resume/chunks ---
    r = await app_client.get("/api/profile/resume/chunks", headers=headers)
    assert r.status_code == 200, r.text
    listed = r.json()["chunks"]
    assert len(listed) == create_body["chunk_count"]

    # Capture embeddings before patch so we can compare after.
    target = listed[0]
    target_id = target["id"]
    embeddings_before = await _load_embeddings_map(db_session)
    assert target_id in embeddings_before

    # --- PATCH /api/profile/resume/chunks/{id} ---
    new_content = "Architected event-driven Python services on Kubernetes with pgvector."
    r = await app_client.patch(
        f"/api/profile/resume/chunks/{target_id}",
        headers=headers,
        json={"content": new_content},
    )
    assert r.status_code == 200, r.text
    patched_chunk = r.json()["chunk"]
    assert patched_chunk["content"] == new_content

    embeddings_after = await _load_embeddings_map(db_session)
    # The patched chunk's embedding must have changed.
    assert embeddings_after[target_id] != embeddings_before[target_id], (
        "PATCH must re-embed the touched chunk"
    )
    # Every *other* chunk's embedding must be byte-identical — re-embed
    # only ran on the single touched chunk per §18.4 "Re-embedding strategy".
    for cid, vec in embeddings_before.items():
        if cid == target_id:
            continue
        assert embeddings_after[cid] == vec, (
            f"chunk {cid} was re-embedded but only {target_id} was edited"
        )

    # --- DELETE /api/profile/resume/chunks/{id} ---
    r = await app_client.delete(
        f"/api/profile/resume/chunks/{target_id}", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True

    # GET should now omit the soft-deleted row.
    r = await app_client.get("/api/profile/resume/chunks", headers=headers)
    assert r.status_code == 200
    remaining_ids = [c["id"] for c in r.json()["chunks"]]
    assert target_id not in remaining_ids


async def test_put_replaces_chunks_and_resets_count(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_login(app_client)
    headers = {"Authorization": f"Bearer {access}"}

    r = await app_client.post(
        "/api/profile/resume",
        headers=headers,
        data={"text": SAMPLE_TEXT},
    )
    assert r.status_code == 201, r.text
    initial_count = r.json()["chunk_count"]
    assert initial_count >= 1

    # PUT with shorter content — fewer chunks; previous chunks soft-deleted.
    r = await app_client.put(
        "/api/profile/resume",
        headers=headers,
        data={"text": "Resume v2: Python engineer focused on backend services."},
    )
    assert r.status_code == 200, r.text
    new_count = r.json()["chunk_count"]
    assert new_count >= 1

    # Live row count should equal ``new_count``.  Verified by hitting GET
    # /chunks (which already filters ``deleted_at IS NULL``).
    r = await app_client.get("/api/profile/resume/chunks", headers=headers)
    listed = r.json()["chunks"]
    assert len(listed) == new_count

    # The DB layer still has the soft-deleted rows for audit.
    deleted_count = (
        await db_session.execute(
            select(MasterResumeChunk).where(
                MasterResumeChunk.deleted_at.is_not(None)
            )
        )
    ).scalars().all()
    assert deleted_count, "PUT must soft-delete the prior chunks"


async def test_get_chunks_with_jd_session_returns_scores(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_and_login(app_client)
    headers = {"Authorization": f"Bearer {access}"}

    r = await app_client.post(
        "/api/profile/resume",
        headers=headers,
        data={"text": SAMPLE_TEXT},
    )
    assert r.status_code == 201, r.text

    # Open a session and attach a JD.
    sr = await app_client.post("/api/sessions")
    session_id = sr.json()["session_id"]
    jd_text = "Senior Python FastAPI engineer with PostgreSQL and Kubernetes."
    jr = await app_client.post(
        f"/api/sessions/{session_id}/jd", json={"jd_text": jd_text}
    )
    assert jr.status_code == 200, jr.text

    r = await app_client.get(
        "/api/profile/resume/chunks",
        headers=headers,
        params={"jd_session_id": session_id},
    )
    assert r.status_code == 200, r.text
    chunks = r.json()["chunks"]
    # Every chunk must carry a similarity score in [-1, 1].
    for c in chunks:
        assert "score" in c
        assert c["score"] is None or -1.0 <= float(c["score"]) <= 1.0


async def _load_embeddings_map(db: AsyncSession) -> dict[str, list[float]]:
    """Return ``{chunk_id_str: embedding_list}`` for all live chunks."""
    rows = (
        await db.execute(
            select(MasterResumeChunk).where(
                MasterResumeChunk.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    out: dict[str, list[float]] = {}
    for r in rows:
        emb = r.embedding
        if emb is None:
            out[str(r.id)] = []
            continue
        # pgvector returns ``numpy.ndarray`` via SQLAlchemy adapter;
        # coerce to a plain list for byte-identical comparison.
        try:
            out[str(r.id)] = list(emb)
        except TypeError:
            out[str(r.id)] = list(emb.tolist())
    return out
