"""Turn a document (PDF or image) into a list of images the model can read."""

from __future__ import annotations

import base64
from pathlib import Path

import pymupdf

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def load_pages(path: Path, dpi: int = 100, max_pages: int = 1) -> list[tuple[str, str]]:
    """Return a list of (mime_type, base64_data), one per page.

    PDFs are rendered to PNG at `dpi`, up to `max_pages` pages.
    Images are returned as-is, as a single page.
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type: {path.name}")

    if suffix == ".pdf":
        pages = []
        with pymupdf.open(path) as pdf:
            for page in list(pdf)[:max_pages]:
                pixmap = page.get_pixmap(dpi=dpi)
                pages.append(("image/png", base64.b64encode(pixmap.tobytes("png")).decode()))
        return pages

    return [(MIME_BY_EXTENSION[suffix], base64.b64encode(path.read_bytes()).decode())]
