"""The studio's writes to a book: book.yaml reordered as text, `pinned:` lists,
keepsakes in extras/, and the HTTP routes that must stay inside the book root."""
import http.client
import io
import json
import shutil
import threading
from pathlib import Path

import pytest
from PIL import Image

from family_cookbook import config, studio

EXAMPLE_YAML = Path(__file__).resolve().parents[1] / "examples" / "fannie-farmer-1896" / "book" / "book.yaml"


def picture(fmt: str = "PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(out, fmt)
    return out.getvalue()


@pytest.fixture
def root(tmp_path):
    """The example's book.yaml with a few entries behind it; the active root,
    since the studio lists entries with render.py's ordering."""
    (tmp_path / "book").mkdir()
    shutil.copy(EXAMPLE_YAML, tmp_path / "book" / "book.yaml")
    for slug in ("chocolate-cake", "indian-pudding", "strawberry-short-cake"):
        folder = tmp_path / "book" / "recipes" / "desserts" / slug
        folder.mkdir(parents=True)
        (folder / "recipe.md").write_text(f"# {slug.replace('-', ' ').title()}\n")
    for slug in ("how-to-combine-ingredients", "how-to-measure"):
        folder = tmp_path / "book" / "sections" / "from-the-cooking-school" / slug
        folder.mkdir(parents=True)
        (folder / "page.md").write_text(f"# {slug}\n")
    root = config.BookRoot(tmp_path)
    config.activate(root)
    return root


def lines(root) -> list[str]:
    return root.config_path.read_text().splitlines()


def test_reordering_chapters_keeps_every_line_and_loads(root):
    before = lines(root)
    order = config.load(root).book_structure
    order.remove("desserts")
    order.insert(order.index("beverages"), "desserts")      # a food chapter, up several places
    order.remove("from-the-cooking-school")
    order.insert(order.index("meat-and-poultry"), "from-the-cooking-school")  # one with a comment above it
    order.remove("title-page")
    order.append("title-page")                               # the first block, to the very end
    studio.reorder_chapters(root, order)
    assert config.load(root).book_structure == order
    after = lines(root)
    assert sorted(after) == sorted(before)                   # every comment and blank line kept
    # The comment directly above a chapter moves with it; the ones under `chapters:` speak for the
    # whole list and stay there; the commented-out index stays at the end of the list.
    school = after.index("  - name: from-the-cooking-school")
    assert after[school - 1] == "  # Farmer opens her book with lessons before recipes; so does this one."
    assert after[after.index("chapters:") + 1].startswith("  # Each matter page is its own chapter")
    assert after.index('  #   label: "Index"') > after.index("  - name: title-page")
    assert after[-1] == "layouts: []"


def test_a_reorder_the_text_cannot_take_leaves_book_yaml_alone(root):
    root.config_path.write_text("chapters: [{name: a}, {name: b}]  # flow style\n")
    before = root.config_path.read_text()
    with pytest.raises(config.ConfigError):
        studio.reorder_chapters(root, ["b", "a"])
    assert root.config_path.read_text() == before
    with pytest.raises(studio.Problem):
        studio.reorder_chapters(root, ["b", "c"])            # not this book's chapters


def test_reordering_entries_writes_the_shortest_pinned_list(root):
    before = lines(root)
    studio.pin_entries(root, "desserts", ["strawberry-short-cake", "chocolate-cake", "indian-pudding"])
    assert config.load(root).by_name["desserts"].pinned == ("strawberry-short-cake",)
    after = lines(root)
    assert after[after.index('    accent: "#9C4A5E"') + 1] == "    pinned: [strawberry-short-cake]"
    assert sorted(set(after) - set(before)) == ["    pinned: [strawberry-short-cake]"]

    # Alphabetical again: the existing list is emptied in place, not deleted with its line.
    studio.pin_entries(root, "from-the-cooking-school", ["how-to-combine-ingredients", "how-to-measure"])
    assert config.load(root).by_name["from-the-cooking-school"].pinned == ()
    assert "    pinned: []" in lines(root)

    s = studio.Studio(root)
    desserts = next(c for c in s.outline()["chapters"] if c["name"] == "desserts")
    assert [e["slug"] for e in desserts["entries"]] == ["strawberry-short-cake", "chocolate-cake", "indian-pudding"]


def test_a_block_pinned_list_becomes_one_line_and_keeps_its_comments(root):
    text = root.config_path.read_text().replace(
        '    accent: "#9C4A5E"\n',
        '    accent: "#9C4A5E"\n    pinned:   # the showpieces first\n      - indian-pudding  # her favorite\n'
        "      - chocolate-cake\n")
    root.config_path.write_text(text)
    studio.pin_entries(root, "desserts", ["chocolate-cake", "strawberry-short-cake", "indian-pudding"])
    assert config.load(root).by_name["desserts"].pinned == ("chocolate-cake", "strawberry-short-cake")
    after = lines(root)
    assert "    pinned: [chocolate-cake, strawberry-short-cake] # the showpieces first" in after
    assert "      # her favorite" in after
    assert not any(line.strip().startswith("- indian-pudding") for line in after)


def test_keepsakes_are_listed_in_extras_md_and_removed_from_it(root):
    s = studio.Studio(root)
    key = "recipes/desserts/indian-pudding"
    extras = root.book / key / "extras"
    s.add_extra(key, "Grandma's Card.PNG", "The original card, about 1950", picture())
    s.add_extra(key, "grandmas-card.png", "  The back of the card  ", picture("JPEG"))
    assert (extras / "extras.md").read_text() == (
        "# Extras\n\n![The original card, about 1950](grandma-s-card.png)\n"
        "![The back of the card](grandmas-card.jpg)\n")
    s.add_extra(key, "grandma-s-card.png", "A third", picture())
    assert (extras / "grandma-s-card-2.png").is_file()

    listed = s.remove_extra(key, "grandma-s-card.png")["listed"]
    assert [k["file"] for k in listed] == ["grandmas-card.jpg", "grandma-s-card-2.png"]
    assert not (extras / "grandma-s-card.png").exists()
    s.remove_extra(key, "grandmas-card.jpg")
    s.remove_extra(key, "grandma-s-card-2.png")
    assert not extras.exists()                               # nothing listed, nothing left: no empty folder

    with pytest.raises(studio.Problem):
        s.add_extra(key, "notes.txt", "A caption", b"not a picture")
    with pytest.raises(studio.Problem):
        s.add_extra(key, "card.png", "", picture())
    assert not extras.exists()


def test_removing_the_last_keepsake_keeps_the_familys_notes(root):
    extras = root.book / "recipes/desserts/chocolate-cake/extras"
    extras.mkdir()
    (extras / "card.jpg").write_bytes(picture("JPEG"))
    (extras / "extras.md").write_text("# Extras\n\nAsk Aunt about the 1960 photo.\n\n![The card](card.jpg)\n")
    studio.Studio(root).remove_extra("recipes/desserts/chocolate-cake", "card.jpg")
    assert (extras / "extras.md").read_text() == "# Extras\n\nAsk Aunt about the 1960 photo.\n\n"


@pytest.fixture
def server(root):
    httpd = studio.serve(root, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=body, headers=headers or {})  # the path goes out as written
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, data


def test_file_routes_and_uploads_stay_inside_the_book(root, server):
    (root.path.parent / "outside.jpg").write_bytes(picture("JPEG"))
    (root.draft).mkdir()
    (root.draft / "cookbook-draft.html").write_text("<p>draft</p>")
    assert request(server, "GET", "/draft/cookbook-draft.html")[0] == 200
    for path in ("/draft/../book/book.yaml", "/draft/..%2fbook%2fbook.yaml", "/book/../../outside.jpg",
                 "/book/%2e%2e/%2e%2e/outside.jpg", "/book/book.yaml", "/file/../../outside.jpg"):
        assert request(server, "GET", path)[0] == 404, path

    status, _ = request(server, "POST", "/api/extras?entry=../..&caption=x&name=a.png", picture())
    assert status == 404
    status, _ = request(server, "POST", "/api/extras?entry=recipes/desserts/../../../..&caption=x&name=a.png",
                        picture())
    assert status == 404
    status, data = request(server, "POST", "/api/extras?entry=recipes/desserts/indian-pudding"
                                           "&caption=A%20card&name=..%2F..%2Fevil.png", picture())
    assert status == 200, data
    assert [k["file"] for k in json.loads(data)["listed"]] == ["evil.png"]
    assert (root.book / "recipes/desserts/indian-pudding/extras/evil.png").is_file()

    status, _ = request(server, "POST", "/api/extras/remove",
                        json.dumps({"entry": "recipes/desserts/indian-pudding", "file": "../recipe.md"}))
    assert status == 404
    assert (root.book / "recipes/desserts/indian-pudding/recipe.md").is_file()


def test_entry_order_over_http_reaches_book_yaml(root, server):
    status, data = request(server, "POST", "/api/entries", json.dumps(
        {"chapter": "desserts", "order": ["indian-pudding", "chocolate-cake", "strawberry-short-cake"]}))
    assert status == 200, data
    assert config.load(root).by_name["desserts"].pinned == ("indian-pudding",)
    status, data = request(server, "POST", "/api/entries", json.dumps(
        {"chapter": "desserts", "order": ["indian-pudding", "missing-cake"]}))
    assert status == 409
    assert "Reload" in json.loads(data)["error"]


def test_proof_state_reports_the_press_files(press_book):
    studio_ = studio.Studio(press_book)
    files = studio_.proof_state()["files"]
    assert files["pages"] == (3 if shutil.which("pdfinfo") else None)
    assert files["interior_bytes"] > 0 and files["cover_bytes"] > 0
    (press_book.draft / "cookbook-cover.pdf").unlink()
    assert studio_.proof_state() == {"files": None}
