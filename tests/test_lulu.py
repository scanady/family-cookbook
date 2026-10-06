import pytest

from family_cookbook.lulu import lulu_inside_margin, spine_width


@pytest.mark.parametrize(("pages", "inches"), [
    (24, 0.25), (84, 0.25), (85, 0.5), (140, 0.5), (141, 0.625), (168, 0.625),
    (169, 0.688), (799, 2.063), (800, 2.125),
])
def test_spine_width_band_edges(pages, inches):
    assert spine_width(pages) == inches


@pytest.mark.parametrize("pages", [23, 801])
def test_spine_width_outside_hardcover_range_exits(pages):
    with pytest.raises(SystemExit, match=str(pages)):
        spine_width(pages)


@pytest.mark.parametrize(("pages", "inches"), [
    (60, 0.5), (61, 0.625), (150, 0.625), (151, 1.0), (400, 1.0),
    (401, 1.125), (600, 1.125), (601, 1.25),
])
def test_inside_margin_band_edges(pages, inches):
    assert lulu_inside_margin(pages) == inches
