"""Lulu's page-count tables: the vendor print geometry the press files are built to.

The engine builds files to Lulu's specification; it does not talk to Lulu. The
tables are vendor measurements that change with the interior page count, not
per-book settings. Lulu's cover template is the final word on the spine: check
it when uploading (docs/PRINTING.md) and fix LULU_HARDCOVER_SPINE here when it
disagrees.
"""
from __future__ import annotations

# Lulu hardcover spine width by interior page count: (last page count in the
# band, spine width in inches). Source: Lulu Book Creation Guide, Hardcover
# Covers table. Hardcover needs at least LULU_HARDCOVER_MIN_PAGES and tops out
# at 800; the renderer pads a shorter book with blank leaves at the back.
LULU_HARDCOVER_MIN_PAGES = 24
LULU_HARDCOVER_SPINE = (
    (84, 0.25), (140, 0.5), (168, 0.625), (194, 0.688), (222, 0.75),
    (250, 0.813), (278, 0.875), (306, 0.938), (334, 1.0), (360, 1.063),
    (388, 1.125), (416, 1.188), (444, 1.25), (472, 1.313), (500, 1.375),
    (528, 1.438), (556, 1.5), (582, 1.563), (610, 1.625), (638, 1.688),
    (666, 1.75), (694, 1.813), (722, 1.875), (750, 1.938), (778, 2.0),
    (799, 2.063), (800, 2.125),
)

# Lulu's recommended total inside (gutter-side) margin, measured from the trim,
# by interior page count: thicker books curve more into the binding. Source:
# Lulu Book Creation Guide, "Gutter Additions".
LULU_INSIDE_MARGIN = ((60, 0.5), (150, 0.625), (400, 1.0), (600, 1.125))
LULU_INSIDE_MARGIN_OVER_600 = 1.25


def spine_width(pages: int) -> float:
    """Lulu's hardcover spine width, in inches, for an interior page count."""
    if pages < LULU_HARDCOVER_MIN_PAGES:
        raise SystemExit(f"Lulu hardcover needs at least {LULU_HARDCOVER_MIN_PAGES} "
                         f"interior pages; the book has {pages}.")
    for last, width in LULU_HARDCOVER_SPINE:
        if pages <= last:
            return width
    raise SystemExit(f"Lulu hardcover allows at most 800 interior pages; the book has {pages}.")


def lulu_inside_margin(pages: int) -> float:
    """Lulu's recommended inside margin, in inches from the trim, for a page count."""
    return next((m for last, m in LULU_INSIDE_MARGIN if pages <= last), LULU_INSIDE_MARGIN_OVER_600)

