from __future__ import annotations

from pathlib import Path


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Decode a plain text resume."""
    return file_bytes.decode("utf-8", errors="replace").strip()
