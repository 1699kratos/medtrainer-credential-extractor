import base64
from pathlib import Path

import pymupdf
import pytest

from credential_extractor.loader import load_pages, page_rotation


def make_pdf(path: Path, pages: int = 1, rotate: int = 0, text: str | None = "Hello license") -> Path:
    """Write a small PDF; text is drawn with the given rotation (0, 90, 180, 270)."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=300, height=400)
        if text:
            for i in range(3):
                page.insert_text((100, 100 + 40 * i), text, fontsize=12, rotate=rotate)
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize(
    "drawn, expected",
    [
        (0, 0),       # normal text: no rotation needed
        (90, 90),     # text runs up the page (dir (0, -1)), as in tx_01 page 1
        (270, 270),   # text runs down the page (dir (0, 1)), as in tx_03
        (180, 180),   # upside down
    ],
)
def test_page_rotation_from_text_direction(tmp_path, drawn, expected):
    pdf = make_pdf(tmp_path / "t.pdf", rotate=drawn)
    with pymupdf.open(pdf) as doc:
        assert page_rotation(doc[0]) == expected


def test_page_rotation_without_text_layer(tmp_path):
    pdf = make_pdf(tmp_path / "blank.pdf", text=None)
    with pymupdf.open(pdf) as doc:
        assert page_rotation(doc[0]) == 0


def test_rotated_page_renders_upright(tmp_path):
    """A page whose text runs sideways comes out with the text horizontal."""
    pdf = make_pdf(tmp_path / "side.pdf", rotate=90)
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        angle = page_rotation(page)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1).prerotate(angle))
    # 300x400 portrait page rotated 270 becomes 400x300
    assert (pix.width, pix.height) == (400, 300)


def test_load_pages_respects_max_pages(tmp_path):
    pdf = make_pdf(tmp_path / "multi.pdf", pages=4)
    assert len(load_pages(pdf, dpi=50, max_pages=3)) == 3
    assert len(load_pages(pdf, dpi=50, max_pages=10)) == 4


def test_load_pages_returns_png_base64(tmp_path):
    pdf = make_pdf(tmp_path / "one.pdf")
    (mime, data), = load_pages(pdf, dpi=50)
    assert mime == "image/png"
    assert base64.b64decode(data)[:8] == b"\x89PNG\r\n\x1a\n"


def test_load_pages_passes_images_through(tmp_path):
    img = tmp_path / "scan.jpg"
    img.write_bytes(b"\xff\xd8\xff fake jpeg")
    (mime, data), = load_pages(img)
    assert mime == "image/jpeg"
    assert base64.b64decode(data) == img.read_bytes()


def test_load_pages_rejects_unsupported_extension(tmp_path):
    bad = tmp_path / "doc.docx"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError, match="unsupported file type"):
        load_pages(bad)
