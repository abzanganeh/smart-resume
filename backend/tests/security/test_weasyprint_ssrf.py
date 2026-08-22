"""PDF export must never fetch an external resource — OWASP LLM10 / A05 (M23 A5).

Resume and cover-letter HTML is built from LLM output and user-supplied
text.  WeasyPrint resolves ``<img src>``, ``<link rel="stylesheet">`` and
CSS ``url()`` while rendering, so a URL that survives into the document
would let an attacker reach cloud metadata endpoints, probe internal
services, read local files, or stall the export worker on a slow host.
This is the SSRF/LFI side of improper output handling, not a formatting
concern.

These tests pin the blocked fetcher's behaviour and prove every export
entry point is wired to it.  No network access is required or permitted:
if the hardening regresses, the recorded-fetch assertions fail rather than
silently dialling out.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest
import weasyprint
from weasyprint.urls import URLFetcherResponse

from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import Session
from app.models.cover_letter import CoverLetterOutput
from app.services.export import assembler
from app.services.export import weasyprint_safe
from app.services.export.weasyprint_safe import (
    BlockedResourceError,
    blocked_url_fetcher,
    render_pdf_bytes,
)
from app.services import export_service

# A live SSRF payload: every URL below is one WeasyPrint would fetch at
# render time if the default fetcher were in play.
METADATA_URL = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
INTERNAL_URL = "https://internal-admin.svc.cluster.local/keys"
LOCAL_FILE_URL = "file:///etc/passwd"

SSRF_HTML = f"""
<html>
  <head>
    <link rel="stylesheet" href="{INTERNAL_URL}">
    <style>body {{ background-image: url({LOCAL_FILE_URL}); }}</style>
  </head>
  <body>
    <img src="{METADATA_URL}">
    <p>Tailored resume body</p>
  </body>
</html>
"""

# 1x1 transparent GIF — the only resource shape an export is allowed to load.
INLINE_GIF = (
    "data:image/gif;base64,"
    + base64.b64encode(
        base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    ).decode()
)


class _FetchRecorder:
    """Stand-in ``url_fetcher`` that records requests instead of making them."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, **kwargs: Any):
        self.urls.append(url)
        return URLFetcherResponse(url=url, body=b"")


@pytest.mark.parametrize(
    "url",
    [
        METADATA_URL,
        INTERNAL_URL,
        LOCAL_FILE_URL,
        "http://localhost:6379/",
        "https://attacker.example.com/beacon.png",
        "ftp://attacker.example.com/payload",
        "//attacker.example.com/protocol-relative.png",
        "logo.png",
    ],
)
def test_external_and_relative_urls_are_blocked(url: str) -> None:
    """OWASP LLM10 — the fetcher refuses anything that leaves the process."""
    with pytest.raises(BlockedResourceError):
        blocked_url_fetcher(url)


def test_blocked_error_does_not_echo_the_url() -> None:
    """OWASP LLM10 — the raised message must not replay attacker-controlled text."""
    with pytest.raises(BlockedResourceError) as excinfo:
        blocked_url_fetcher(METADATA_URL)

    assert METADATA_URL not in str(excinfo.value)
    assert excinfo.value.url == METADATA_URL


def test_inline_data_uri_is_allowed() -> None:
    """OWASP LLM10 — inline payloads still render, so legitimate exports work."""
    response = blocked_url_fetcher(INLINE_GIF)

    assert response.content_type == "image/gif"
    response.close()


def test_ssrf_payload_is_live_under_the_default_fetcher() -> None:
    """Control case: the payload really does trigger fetches, so the block matters."""
    recorder = _FetchRecorder()
    weasyprint.HTML(string=SSRF_HTML, url_fetcher=recorder).write_pdf()

    assert any(METADATA_URL in url for url in recorder.urls)
    assert any(LOCAL_FILE_URL in url for url in recorder.urls)


def test_render_pdf_bytes_blocks_ssrf_payload_and_still_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OWASP LLM10 — no fetch escapes, and the export does not fail closed."""
    fetched: list[str] = []

    def _recording_inline_fetcher(timeout: int, ssl_context: Any):
        class _Recorder:
            def fetch(self, url: str, headers: Any = None):
                fetched.append(url)
                return URLFetcherResponse(url=url, body=b"")

        return _Recorder()

    monkeypatch.setattr(
        weasyprint_safe, "_inline_url_fetcher", _recording_inline_fetcher
    )

    pdf = render_pdf_bytes(SSRF_HTML, css=[f"h1 {{ background: url({METADATA_URL}); }}"])

    assert pdf.startswith(b"%PDF-")
    assert fetched == []


def _session_with_ssrf_content() -> Session:
    """A session whose LLM-authored fields carry SSRF bait in every URL slot."""
    return Session(
        session_id="ssrf-session",
        jd_raw="Senior Engineer",
        phase3_output=TailoredResumeOutput(
            contact={
                "name": "Jane Doe",
                "email": "jane@example.com",
                "website": METADATA_URL,
                "linkedin": INTERNAL_URL,
                "github": LOCAL_FILE_URL,
            },
            summary=f'Engineer <img src="{METADATA_URL}">',
            skills=["Cloud: AWS, GCP"],
            experience=[
                TailoredExperienceEntry(
                    company="Acme",
                    title="Engineer",
                    dates="2020-2024",
                    bullets=[f'Built systems <img src="{INTERNAL_URL}">'],
                )
            ],
            projects=[{"name": "Portfolio", "url": METADATA_URL, "bullets": ["Shipped it"]}],
        ),
        cover_letter_output=CoverLetterOutput(
            body_markdown=f'Dear team <img src="{METADATA_URL}">\n\nRegards.',
            body_plain=f'Dear team <img src="{METADATA_URL}">\n\nRegards.',
            word_count=5,
            tone="balanced",
        ),
    )


@pytest.mark.parametrize(
    "render",
    [
        pytest.param(
            lambda: asyncio.run(export_service.render_pdf(_session_with_ssrf_content())),
            id="resume_pdf",
        ),
        pytest.param(
            lambda: asyncio.run(
                export_service.render_cover_letter_pdf(_session_with_ssrf_content())
            ),
            id="cover_letter_pdf",
        ),
        pytest.param(
            lambda: asyncio.run(
                assembler._master_resume_pdf(f'Resume <img src="{METADATA_URL}">')
            ),
            id="master_resume_pdf",
        ),
    ],
)
def test_every_export_entry_point_uses_the_blocked_fetcher(
    render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OWASP LLM10 — no export path may construct a default-fetcher document."""
    seen_fetchers: list[Any] = []
    real_html = weasyprint.HTML

    def _recording_html(**kwargs: Any):
        seen_fetchers.append(kwargs.get("url_fetcher"))
        return real_html(**kwargs)

    monkeypatch.setattr(weasyprint, "HTML", _recording_html)
    monkeypatch.setattr(
        weasyprint_safe,
        "_inline_url_fetcher",
        lambda timeout, ssl_context: pytest.fail("export attempted a real fetch"),
    )

    pdf = render()

    assert pdf.startswith(b"%PDF-")
    assert seen_fetchers == [blocked_url_fetcher]


def test_resume_html_escapes_injected_image_tags() -> None:
    """OWASP LLM10 / A05 — LLM-authored text is escaped, so it cannot add new elements."""
    html = export_service._resume_to_html(_session_with_ssrf_content())

    assert "<img" not in html
    assert "&lt;img" in html
