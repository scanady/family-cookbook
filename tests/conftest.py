from pathlib import Path

import pytest
from PIL import Image

from family_cookbook import config


def write_pdf(path: Path, pages: int, inches: tuple[float, float]) -> None:
    """A blank PDF of `pages` pages, each `inches` wide and high."""
    width, height = (round(x * 72) for x in inches)
    leaves = [Image.new("RGB", (width, height), "white") for _ in range(pages)]
    leaves[0].save(path, "PDF", resolution=72, save_all=True, append_images=leaves[1:])


@pytest.fixture
def press_book(tmp_path):
    """A book root with its press PDFs built: a 3-page interior and a 19 x 12.75 in cover."""
    (tmp_path / "book").mkdir()
    (tmp_path / "book" / "book.yaml").write_text('book:\n  title: "Test Kitchen"\n')
    (tmp_path / "draft").mkdir()
    write_pdf(tmp_path / "draft" / "cookbook-interior-press.pdf", 3, (8.75, 11.25))
    write_pdf(tmp_path / "draft" / "cookbook-cover.pdf", 1, (19.0, 12.75))
    return config.BookRoot(tmp_path)
