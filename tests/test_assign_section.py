import pytest

from family_cookbook import config


@pytest.fixture(scope="module")
def render(tmp_path_factory):
    """render.py reads the active book root on import, so give it one."""
    root = tmp_path_factory.mktemp("book")
    (root / "book").mkdir()
    (root / "book" / "book.yaml").write_text(
        "chapters:\n  - name: mains\n    kind: recipes\n", encoding="utf-8")
    images = root / "book" / "recipes" / "mains" / "stew" / "images"
    images.mkdir(parents=True)
    (images / "stew.jpg").write_bytes(b"")
    config.activate(config.BookRoot(root))
    from family_cookbook import render
    return render


def test_photo_no_frame_suits_does_not_cost_a_second_page(render, monkeypatch):
    # The text fits one page only beside the sidebar column, and the photo
    # breaks every frame's rules: the recipe keeps its one page, in the column.
    monkeypatch.setattr(render, "holds_at_full_type", lambda r, a: a == "Sidebar Portrait")
    monkeypatch.setattr(render, "photo_fit",
                        lambda r, a: render.PhotoFit((0, 0, 1, 1), "cuts the food", 0.4))
    r = render.Recipe("mains", "stew", "", "", ingredients=["beef"], directions=["Simmer."])
    render.assign_section([r], ("", ""))
    assert r.archetype == "Sidebar Portrait"
