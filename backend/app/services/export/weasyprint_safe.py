"""Locked-down WeasyPrint rendering for every export path (OWASP LLM10 / A05).

Resume and cover-letter HTML is assembled from LLM output and from
user-supplied text, and WeasyPrint resolves ``<img src>``,
``<link rel="stylesheet">`` and CSS ``url()`` references while it renders.
The stock fetcher follows ``http(s)://`` and ``file://``, so a URL that
survives into the document turns the export worker into a blind SSRF probe
(cloud metadata endpoints, internal services) or a local-file read, and an
attacker-chosen host can stall or flood the renderer.

All PDF rendering therefore goes through :func:`render_pdf_bytes` (or
:func:`safe_html` / :func:`safe_css`), which wire the document to
:func:`blocked_url_fetcher`.  That fetcher serves inline ``data:`` URIs and
refuses everything else.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import structlog

log = structlog.get_logger("export.weasyprint")

#: Only inline payloads are resolvable during a render.  Anything that would
#: leave the process (http, https, ftp) or touch the filesystem (file) is
#: refused, as are relative references, which resolve against ``base_url``.
ALLOWED_URL_SCHEMES = frozenset({"data"})


class BlockedResourceError(Exception):
    """Raised when a document asks WeasyPrint to fetch a non-``data:`` URL.

    WeasyPrint catches fetch errors per resource, so raising this degrades
    the affected image or stylesheet instead of failing the whole export.
    """

    def __init__(self, url: str, scheme: str) -> None:
        self.url = url
        self.scheme = scheme
        super().__init__(
            "blocked external resource fetch during PDF render "
            f"(scheme={scheme or 'relative'!r})"
        )


def _inline_url_fetcher(timeout: int, ssl_context: Any):
    """WeasyPrint fetcher restricted to inline data, built lazily per call."""
    from weasyprint.urls import URLFetcher

    return URLFetcher(
        timeout=timeout,
        ssl_context=ssl_context,
        allowed_protocols=tuple(ALLOWED_URL_SCHEMES),
        allow_redirects=False,
    )


def blocked_url_fetcher(
    url: str,
    timeout: int = 10,
    ssl_context: Any = None,
    **kwargs: Any,
):
    """WeasyPrint ``url_fetcher`` that resolves ``data:`` URIs and nothing else."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in ALLOWED_URL_SCHEMES:
        return _inline_url_fetcher(timeout, ssl_context).fetch(url)

    # The URL itself may carry user or LLM content, so only the routing
    # parts are logged.
    log.warning(
        "export.pdf.resource_blocked",
        scheme=scheme or "relative",
        host=parts.netloc or "",
    )
    raise BlockedResourceError(url, scheme)


def safe_html(html: str, *, base_url: str | None = None):
    """Build a WeasyPrint ``HTML`` document with external fetching disabled."""
    from weasyprint import HTML

    return HTML(string=html, base_url=base_url, url_fetcher=blocked_url_fetcher)


def safe_css(css: str, *, base_url: str | None = None):
    """Build a WeasyPrint ``CSS`` sheet with external fetching disabled."""
    from weasyprint import CSS

    return CSS(string=css, base_url=base_url, url_fetcher=blocked_url_fetcher)


def render_pdf_bytes(
    html: str,
    *,
    css: Sequence[str] = (),
    base_url: str | None = None,
) -> bytes:
    """Render ``html`` to PDF bytes with every external resource blocked."""
    document = safe_html(html, base_url=base_url)
    return document.write_pdf(
        stylesheets=[safe_css(sheet, base_url=base_url) for sheet in css]
    )


__all__ = [
    "ALLOWED_URL_SCHEMES",
    "BlockedResourceError",
    "blocked_url_fetcher",
    "render_pdf_bytes",
    "safe_css",
    "safe_html",
]
