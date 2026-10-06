import io
from types import SimpleNamespace

import pytest
from PIL import Image

from family_cookbook import photo


def png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, "PNG")
    return out.getvalue()


@pytest.mark.parametrize("size", [(3584, 4800), (4800, 3584), (2400, 4800)])
def test_every_generated_shape_becomes_an_8_by_11_master(tmp_path, size):
    w, h = photo.to_master(png(*size), tmp_path / "master.jpg")
    assert abs(w / h - 8 / 11) < 0.001
    assert w <= size[0] and h <= size[1]  # cut, never scaled up
    with Image.open(tmp_path / "master.jpg") as img:
        assert img.size == (w, h) and img.info["dpi"] == pytest.approx((300, 300))


def recipe(tmp_path, body: str):
    (tmp_path / "recipe.md").write_text(body, encoding="utf-8")
    return SimpleNamespace(folder=tmp_path, slug="gingerbread", title="Spicy Gingerbread")


def test_the_photo_line_goes_before_the_metadata_once(tmp_path):
    r = recipe(tmp_path, "# Spicy Gingerbread\n\n*Shirley G*\n\n- **Category:** Desserts\n\n## Ingredients\n\n- 2 eggs\n")
    photo.link_photo(r)
    photo.link_photo(r)
    assert (tmp_path / "recipe.md").read_text(encoding="utf-8") == (
        "# Spicy Gingerbread\n\n*Shirley G*\n\n![Spicy Gingerbread](images/gingerbread.jpg)\n\n"
        "- **Category:** Desserts\n\n## Ingredients\n\n- 2 eggs\n"
    )


def test_a_recipe_without_metadata_gets_the_line_before_its_first_section(tmp_path):
    r = recipe(tmp_path, "# Spicy Gingerbread\n\n## Ingredients\n\n- 2 eggs\n")
    photo.link_photo(r)
    assert (tmp_path / "recipe.md").read_text(encoding="utf-8").startswith(
        "# Spicy Gingerbread\n\n![Spicy Gingerbread](images/gingerbread.jpg)\n\n## Ingredients"
    )
