"""Load the print HTML and report any page whose content overflows its box, or
whose reading text prints below the readability floor.

FIT_SCRIPT zooms a page whose content would overflow, so a page can fit and
still print too small. Every line of reading text — ingredients, directions,
notes, and prose paragraphs and lists — is measured at its effective size,
computed font size times the zoom applied to it, and any page below MIN_TEXT_PT
fails. Ingredient subheads are small caps labels, not reading text, and are not
measured.

Each failing page is reported in plain words: the entry on it, what is wrong,
and how to fix it. The measurements behind each failure are kept for
`cookbook check --verbose`."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from . import config
from .export import launch_chromium

MIN_TEXT_PT = 10

ISSUES_URL = "https://github.com/scanady/family-cookbook/issues"

JS = """
(minTextPt) => {
  const out = [];
  document.querySelectorAll('section.page').forEach((pg, i) => {
    const issues = [];
    let overflow = false;
    // page box itself
    if (pg.scrollHeight > pg.clientHeight + 1) issues.push(`page scrollH ${pg.scrollHeight} > ${pg.clientHeight}`);
    if (pg.scrollWidth > pg.clientWidth + 1) issues.push(`page scrollW ${pg.scrollWidth} > ${pg.clientWidth}`);
    overflow = issues.length > 0;
    // any descendant clipped beyond the page rect
    const pr = pg.getBoundingClientRect();
    pg.querySelectorAll('*').forEach(el => {
      if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      const over = [];
      if (r.bottom > pr.bottom + 0.5) over.push(`bottom +${(r.bottom - pr.bottom).toFixed(1)}px`);
      if (r.right > pr.right + 0.5) over.push(`right +${(r.right - pr.right).toFixed(1)}px`);
      if (r.top < pr.top - 0.5) over.push(`top -${(pr.top - r.top).toFixed(1)}px`);
      if (r.left < pr.left - 0.5) over.push(`left -${(pr.left - r.left).toFixed(1)}px`);
      if (over.length) {
        overflow = true;
        const tag = el.className && typeof el.className === 'string' ? el.className.split(' ')[0] : el.tagName;
        const txt = (el.textContent || '').trim().slice(0, 40);
        issues.push(`<${el.tagName.toLowerCase()}.${tag}> ${over.join(',')} "${txt}"`);
      }
    });
    // reading text at its effective printed size: computed size x applied zoom,
    // to the hundredth so 13.333px (10pt) is not read as 9.99999pt
    let smallest = Infinity;
    pg.querySelectorAll('ul.ingredients li:not(.subhead), ol.directions li, ul.notes li, .prose p, .prose-list li').forEach(li => {
      const pt = Math.round(parseFloat(getComputedStyle(li).fontSize) * 0.75 * li.currentCSSZoom * 100) / 100;
      if (pt < smallest) smallest = pt;
    });
    if (smallest < minTextPt) issues.push(`text ${smallest}pt < ${minTextPt}pt`);
    if (issues.length) {
      const tagEl = pg.querySelector('.page-tag');
      const numEl = pg.querySelector('.page-number');
      out.push({idx: i + 1, id: pg.id, num: numEl ? numEl.textContent : '', tag: tagEl ? tagEl.textContent : '',
                overflow, small_pt: smallest < minTextPt ? smallest : null, issues: issues.slice(0, 8)});
    }
  });
  return out;
}
"""


def failing_pages(html: Path) -> list[dict]:
    """Every page of a print HTML file that overflows or prints reading text
    below MIN_TEXT_PT: {idx (PDF page), num (the folio, '' if none), tag,
    issues (the measurements), entry, key, problem, fix}. `entry` names what is
    on the page and `key` is its folder under book/ ('' when it has none or the
    book is not active); `problem` and `fix` are plain sentences."""
    if not html.is_file():
        raise SystemExit(f"{html} not found — run: cookbook build --print")
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page()
        page.goto(html.resolve().as_uri(), wait_until="networkidle", timeout=300_000)
        page.evaluate("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(8_000)
        page.emulate_media(media="print")
        page.wait_for_timeout(1_000)
        results = page.evaluate(JS, MIN_TEXT_PT)
        browser.close()
    if results:
        pages = _book_pages()
        for r in results:
            r.update(explain(r, pages))
    return results


def _book_pages() -> list:
    """The active book's pages in print order, or [] when no book is active."""
    try:
        config.active_root()
    except RuntimeError:
        return []
    from . import render

    return render.build(render.assemble_recipes())[1]


def explain(result: dict, pages: list) -> dict:
    """The plain-language fields of one failing page: what is on it, what is
    wrong, and what to do. `pages` is the book in print order; a page is named
    only when the print HTML still matches it (same page at that position)."""
    r = pages[result["idx"] - 1] if result["idx"] <= len(pages) else None
    if r is not None and result["id"] != f"p{r.page_number}":
        r = None

    small = result["small_pt"]
    if result["overflow"] and small is not None:
        problem = (f"Text runs past the edge of the page even shrunk to {small:g} pt, below the "
                   f"{MIN_TEXT_PT} pt minimum: the page holds far too much.")
    elif result["overflow"]:
        problem = "Text runs past the edge of the page."
    else:
        problem = (f"Text would print at {small:g} pt, below the {MIN_TEXT_PT} pt minimum: the page "
                   "holds too much, so its text shrinks to fit.")

    if r is None:
        fix = ("The print layout does not match the book: run cookbook build --print, then "
               "cookbook check again, to see which entry is on this page." if pages else
               "Run cookbook check from the book's folder to see which entry is on this page.")
        return {"entry": "", "key": "", "problem": problem, "fix": fix}

    from . import render

    rel = r.md_path.relative_to(render.BOOK_ROOT.path).as_posix() if not r.is_generated else ""
    key = "" if r.is_generated else r.folder.relative_to(render.BOOK).as_posix()
    if r.is_generated:
        entry = f"the {r.title} page"
        fix = f"The engine lays this page out itself, so this is a bug: please report it at {ISSUES_URL}."
    elif r.is_divider:
        entry = f"the opening page of {r.title} ({rel})"
        fix = f"Shorten the chapter's opening message in {rel}."
    elif r.is_keepsake:
        entry = f"the keepsake page of {r.title} ({r.category}/{r.slug})"
        fix = f"Shorten the captions in {key}/extras/extras.md."
    elif r.base != "recipes" or r.is_chapter_page:
        entry = f"{r.title} ({rel})"
        fix = f"Shorten the text in {rel}."
    else:
        entry = f"{r.title} ({r.category}/{r.slug})"
        fix = _recipe_fix(r)
    return {"entry": entry, "key": key, "problem": problem, "fix": fix}


def _recipe_fix(r) -> str:
    """How to make a recipe fit, given the layout it is on and who chose it."""
    from . import render

    shorten = ("shorten it: trim the directions, or move stories from its Notes into the "
               "original (sources/recipe-original.md), which keeps them without printing them")

    def row(archetype: str) -> str:
        if r.origin == "curated":
            return f"set `archetype: {archetype}` in its `layouts:` row in book/book.yaml"
        return (f"add a `layouts:` row to book/book.yaml with chapter: {r.category}, "
                f"slug: {r.slug}, archetype: {archetype}")

    if r.archetype == render.RECIPE_SPREAD[0]:
        return f"Two facing pages are the most one recipe can have, and this one already has them, so {shorten}."
    if r.archetype == render.TWO_PAGE_SPREAD[0]:
        return (f"Two facing pages are the most one recipe can have. To spread the text over both, "
                f"{row(render.RECIPE_SPREAD[0])}; otherwise {shorten}.")
    if r.archetype == "Inset Original":
        return ("Shorten the original in sources/recipe-original.md or the recipe, or choose "
                "another layout in its `layouts:` row in book/book.yaml.")
    return ("Shorten the recipe, move stories from its Notes into the original "
            "(sources/recipe-original.md), or give it a two-page layout: "
            f"{row(render.RECIPE_SPREAD[0])}.")


def report(results: list[dict], verbose: bool = False) -> int:
    """Print failing_pages()'s results; 1 when any page fails, else 0. Verbose
    adds the layout and the measurements behind each failure."""
    if not results:
        print(f"No overflow and no reading text below {MIN_TEXT_PT} pt on any page.")
        return 0
    for r in results:
        where = f"Page {r['num']}" if r["num"] else f"PDF page {r['idx']}"
        print(f"{where}: {r['entry']}" if r["entry"] else where)
        print(f"   {r['problem']}")
        print(f"   Fix: {r['fix']}")
        if verbose:
            print(f"   PDF page {r['idx']}, layout: {r['tag']}")
            for i in r["issues"]:
                print(f"     {i}")
    if not verbose:
        print("\n(cookbook check --verbose shows the measurements behind each failure.)")
    return 1


def main(html: Path, verbose: bool = False) -> int:
    """Check one print HTML file; 1 when any page fails, else 0."""
    return report(failing_pages(html), verbose)
