from __future__ import annotations

import io

import pdfplumber

UNREADABLE_PDF_MESSAGE = (
    "Could not read this PDF. The file may be corrupted, password-protected, "
    "or not a valid PDF. Try pasting your resume as text, or upload a DOCX or TXT file."
)


class UnreadablePdfError(ValueError):
    """PDF bytes could not be parsed (corrupt, encrypted, or not a PDF)."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from a PDF file."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
    except Exception as exc:
        raise UnreadablePdfError(UNREADABLE_PDF_MESSAGE) from exc
    return "\n".join(pages)
