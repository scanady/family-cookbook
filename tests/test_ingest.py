from pathlib import Path

import pytest

from family_cookbook import ingest, models


class PageReader:
    """A stand-in model that reads a document of known entries: each call sees
    only the entries, or the parts of entries, on the pages it is given."""

    def __init__(self, entries: dict[str, list[int]]) -> None:
        self.entries = entries
        self.name = "page-reader"

    def json(self, prompt, schema, images=()):
        shown = [int(p.stem) for p in images]
        found = []
        for title, pages in self.entries.items():
            visible = [n for n in pages if n in shown]
            if visible:
                found.append({
                    "title": title, "kind": "recipe", "pages": [shown.index(n) + 1 for n in visible],
                    "verbatim": f"{title} {visible}", "complete": visible == pages, "incomplete_reason": "",
                })
        return {"entries": found}, models.Usage(10, 10, 0.01)


def read(entries: dict[str, list[int]], page_count: int) -> dict[str, list[int]]:
    pages = [(n, ingest.Page(Path(f"{n}.jpg"), f"p. {n}")) for n in range(1, page_count + 1)]
    found, unread = ingest.transcribe(PageReader(entries), pages)
    assert unread == []
    titles = [e.title for e in found]
    assert len(titles) == len(set(titles)), f"an entry came back twice: {titles}"
    return {e.title: e.pages for e in found}


def test_entries_across_window_breaks_come_back_once_and_whole():
    document = {"A": [1], "B": [2, 3], "C": [6, 7], "D": [7], "E": [8, 9, 10, 11, 12, 13], "F": [14]}
    assert read(document, 14) == document


def test_an_entry_longer_than_a_window_is_read_whole():
    document = {"A": list(range(1, ingest.WINDOW + 4)), "B": [ingest.WINDOW + 4]}
    assert read(document, ingest.WINDOW + 4) == document


def test_every_call_is_charged():
    pages = [(n, ingest.Page(Path(f"{n}.jpg"), f"p. {n}")) for n in range(1, 9)]
    found, _ = ingest.transcribe(PageReader({"A": [1], "B": [6, 7], "C": [8]}), pages)
    assert sum(e.usage.cost_usd for e in found) == pytest.approx(0.02)


class RefusesPage(PageReader):
    """Refuses any read that includes one page, as a recitation filter does."""

    def __init__(self, entries, refused: int) -> None:
        super().__init__(entries)
        self.refused = refused

    def json(self, prompt, schema, images=()):
        if self.refused in [int(p.stem) for p in images]:
            raise models.Refused("no answer (RECITATION)")
        return super().json(prompt, schema, images)


def test_a_refused_page_is_skipped_and_the_rest_still_read():
    pages = [(n, ingest.Page(Path(f"{n}.jpg"), f"p. {n}")) for n in range(1, 10)]
    found, unread = ingest.transcribe(RefusesPage({"A": [1], "B": [2, 3], "C": [4], "D": [8, 9]}, refused=4), pages)
    assert unread == [4]
    assert {e.title: e.pages for e in found} == {"A": [1], "B": [2, 3], "D": [8, 9]}


SOURCE = "1- 8 ¼ oz. Can crushed pineapple\n1 ¾ Cups Milk\n2½ c flour\nBake 350 degrees. Serves six"


def fields(items, yield_="Not specified", temperature="Not specified"):
    return {"ingredient_groups": [{"heading": "", "items": items}], "yield": yield_, "temperature": temperature}


def test_amounts_the_source_states_pass_in_any_spelling():
    clean = fields(["1 (8 1/4 oz.) can crushed pineapple", "1 3/4 cups milk", "3/4 cup", "2 1/2 cups flour"],
                   yield_="6 servings", temperature="350°F")
    assert ingest.unsupported_numbers(SOURCE, clean) == []


def test_a_changed_or_invented_amount_is_flagged():
    clean = fields(["1 (8 3/4 oz.) can crushed pineapple"], yield_="About 12 servings", temperature="375°F")
    problems = ingest.unsupported_numbers(SOURCE, clean)
    assert [p.split(":")[-1].strip() for p in problems] == [
        "12 not in the source", "375 not in the source", "8 3/4 not in the source",
    ]


def test_a_misread_of_the_page_is_caught_against_the_pdf_text():
    assert ingest.misread_numbers("1- 8 ¾ oz. Can", SOURCE) == ["8 3/4"]
    assert ingest.misread_numbers("1-1/2 cups", "1 ½ cups") == []
