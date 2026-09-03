"""PDF resume parser error handling."""

from __future__ import annotations

import pytest

from app.parsers.pdf_parser import UNREADABLE_PDF_MESSAGE, UnreadablePdfError, extract_text_from_pdf


def test_extract_text_from_pdf_rejects_invalid_bytes() -> None:
    with pytest.raises(UnreadablePdfError, match="Could not read this PDF"):
        extract_text_from_pdf(b"not-a-pdf")


def test_unreadable_pdf_message_suggests_alternatives() -> None:
    msg = UNREADABLE_PDF_MESSAGE.lower()
    assert "pasting" in msg or "paste" in msg
    assert "docx" in msg
