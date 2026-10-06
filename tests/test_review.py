import json

import pytest

from family_cookbook import config, review


@pytest.fixture
def book(tmp_path):
    for slug in ("pie", "cake"):
        folder = tmp_path / "book" / "recipes" / "desserts" / slug
        (folder / "sources").mkdir(parents=True)
        (folder / "recipe.md").write_text(f"# {slug.title()}\n\n## Ingredients\n\n- 1 egg\n\n## Directions\n\n1. Bake.\n", encoding="utf-8")
        (folder / "sources" / "recipe-original.md").write_text("```text\n1 egg. Bake.\n```\n", encoding="utf-8")
    (tmp_path / "book" / "book.yaml").write_text("book:\n  title: T\n", encoding="utf-8")
    return review.Book(config.BookRoot(tmp_path))


def approve(book, entry, seconds, edited=False):
    text = (book.root.book / entry / "recipe.md").read_text(encoding="utf-8")
    book.log.parent.mkdir(parents=True, exist_ok=True)
    with book.log.open("a") as f:
        f.write(json.dumps({"entry": entry, "seconds": seconds, "edited": edited, "sha": review._sha(text)}) + "\n")


def waiting(book):
    return [q["entry"] for q in book.queue(everything=False)]


def test_an_approved_recipe_returns_to_the_queue_when_it_changes(book):
    assert waiting(book) == ["recipes/desserts/cake", "recipes/desserts/pie"]
    approve(book, "recipes/desserts/pie", 40)
    assert waiting(book) == ["recipes/desserts/cake"]
    md = book.root.book / "recipes/desserts/pie/recipe.md"
    md.write_text(md.read_text(encoding="utf-8").replace("1 egg", "2 eggs"), encoding="utf-8")
    assert waiting(book) == ["recipes/desserts/cake", "recipes/desserts/pie"]


def test_the_review_average_counts_each_ingested_recipe_once(book):
    log = book.root.book / "sources" / "ai-log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"command": "ingest", "entry": "recipes/desserts/pie"}) + "\n", encoding="utf-8")
    approve(book, "recipes/desserts/pie", 90, edited=True)
    approve(book, "recipes/desserts/pie", 10)   # a second look later is not more correction time
    approve(book, "recipes/desserts/cake", 5)   # typed in by hand, not ingested: not in the sample
    assert book.stats() == {"reviewed": 1, "edited": 1, "average_seconds": 90, "target_seconds": 120}
