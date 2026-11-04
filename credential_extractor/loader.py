"""Turn a document (PDF or image) into a list of images the model can read."""

from __future__ import annotations

import base64
from collections import Counter
from pathlib import Path

import pymupdf

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# Writing direction of a text line -> rotation (degrees, clockwise) that puts it upright.
# (1, 0) left-to-right, (0, -1) runs up the page, (0, 1) runs down, (-1, 0) upside down.
ROTATION_BY_DIRECTION = {(1, 0): 0, (0, -1): 90, (0, 1): 270, (-1, 0): 180}


def page_rotation(page: pymupdf.Page) -> int:
    """Rotation needed to make the page's text upright, from its text layer.

    Uses the majority writing direction of the OCR/text lines. Pages without a
    text layer (plain scans) return 0: there is nothing to infer from.
    """
    directions: Counter = Counter()
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            dx, dy = line["dir"]
            directions[(round(dx), round(dy))] += 1
    if not directions:
        return 0
    majority = directions.most_common(1)[0][0]
    return ROTATION_BY_DIRECTION.get(majority, 0)


def render_page(page: pymupdf.Page, dpi: int, fix_rotation: bool = True) -> bytes:
    """Render one page to PNG at `dpi`, rotated upright when fix_rotation is set."""
    angle = page_rotation(page) if fix_rotation else 0
    matrix = pymupdf.Matrix(dpi / 72, dpi / 72).prerotate(angle)
    return page.get_pixmap(matrix=matrix).tobytes("png")


def load_pages(
    path: Path, dpi: int = 100, max_pages: int = 1, fix_rotation: bool = True
) -> list[tuple[str, str]]:
    """Return a list of (mime_type, base64_data), one per page.

    PDFs are rendered to PNG at `dpi`, up to `max_pages` pages, each rotated
    upright according to its text layer. Images are returned as-is, as a
    single page (no rotation fix: there is no text layer to read).
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type: {path.name}")

    if suffix == ".pdf":
        pages = []
        with pymupdf.open(path) as pdf:
            for page in list(pdf)[:max_pages]:
                png = render_page(page, dpi, fix_rotation)
                pages.append(("image/png", base64.b64encode(png).decode()))
        return pages

    return [(MIME_BY_EXTENSION[suffix], base64.b64encode(path.read_bytes()).decode())]
