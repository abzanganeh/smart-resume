from __future__ import annotations

import io

from docx import Document


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from a DOCX file, preserving paragraph structure."""
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)
