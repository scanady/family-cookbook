"""Check the book/ spec for structural problems the renderer will not catch.

render.py is forgiving by design: a recipe folder missing `recipe.md` is
skipped silently, a manifest row for a slug that no longer exists is ignored,
and a broken image link renders as a placeholder. Those are the right defaults
for a build, and the wrong ones for review — the book still renders, just with
a page quietly missing. This module surfaces them instead.

Conventions checked here are the ones written down in the book's
`.github/instructions/recipe-content.instructions.md` and
`.github/instructions/book-pages.instructions.md`, and the engine's
`.github/instructions/cookbook-layout.instructions.md`. Structural knowledge
(book order, page categories, archetype names) is imported from render.py
rather than restated, so the two cannot drift apart.

Usage:
    cookbook lint              # report everything
    cookbook lint --errors     # errors only, skip warnings
    cookbook lint --quiet      # exit code only, no output

Exit status is 1 when any error is found, 0 otherwise. Warnings never fail.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import config, render

ROOT = render.ROOT
BOOK = render.BOOK

# Suffixes `cookbook fit` derives from a canonical photo. They are gitignored and
# must never be hand-edited, so the linter treats them as expected-but-not-source.
DERIVED_SUFFIXES = ("hero", "half", "sidebar", "inset", "dense", "spread")

REQUIRED_RECIPE_HEADINGS = ("## Ingredients", "## Directions")

# Metadata keys the recipe template offers. All are optional, but a key outside
# this set is nearly always a typo ("Prep Time:", "Serves:") that renders as a
# stray chip instead of the intended field. "Image position" is not a chip — it
# is a manual override of where the photo's crop sits (render.py
# POSITION_GRAVITY), set only where the automatic subject detection misjudges.
KNOWN_META_KEYS = {
    "Category", "Cuisine", "Yield", "Prep time", "Cook time", "Temperature",
    "Chill time", "Total time", "Source", "Image position",
}

# Values render.py understands for the "Image position" key.
IMAGE_POSITIONS = {"top", "center", "bottom"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    @property
    def ok(self) -> bool:
        return not self.errors


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------- entries


# A chapter's own page may carry a photo and a verbatim transcription beside it
# (book/sections/{chapter}/images/, sources/), which render.py reads, and
# its keepsakes (extras/). Those folders are the chapter's assets, not entries.
CHAPTER_ASSET_DIRS = ("images", "sources", "extras")


def entry_folders(catdir: Path) -> list[Path]:
    """The entry folders of one chapter, skipping a chapter page's asset folders."""
    skip = CHAPTER_ASSET_DIRS if catdir.parent == BOOK / "sections" else ()
    return sorted(p for p in catdir.iterdir() if p.is_dir() and p.name not in skip)


def entry_dirs(base: Path) -> list[tuple[str, Path]]:
    """(chapter, folder) for every entry under a recipes/ or sections/ base.

    A chapter's own page is book/sections/{chapter}/page.md and is not an entry
    — entries are always one level further down, in a {slug}/ folder.
    """
    if not base.is_dir():
        return []
    found = []
    for catdir in sorted(p for p in base.iterdir() if p.is_dir()):
        for slugdir in entry_folders(catdir):
            found.append((catdir.name, slugdir))
    return found


def chapter_pages() -> list[Path]:
    """Chapter pages: book/sections/{chapter}/page.md, one per chapter at most."""
    registry = BOOK / "sections"
    if not registry.is_dir():
        return []
    return sorted(p / "page.md" for p in registry.iterdir()
                  if p.is_dir() and (p / "page.md").exists())


def check_entry(rep: Report, slugdir: Path, md_name: str, source_name: str) -> None:
    slug = slugdir.name
    where = rel(slugdir)
    md = slugdir / md_name

    if not md.exists():
        rep.error(where, f"missing {md_name} — the renderer skips this folder silently")
        return

    if slug != slug.lower() or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        rep.error(where, f"slug {slug!r} is not lowercase-kebab-case")

    text = md.read_text(encoding="utf-8")
    lines = text.splitlines()

    # A page must open with an H1; render.py takes the title from it. A
    # chapter's own page is not an entry and takes its heading from book.yaml —
    # check_divider_titles() rejects an H1 there instead.
    first = next((l for l in lines if l.strip()), "")
    if not first.startswith("# "):
        rep.error(f"{where}/{md_name}", "does not start with an H1 title line")

    check_images(rep, slugdir, slug, text)
    check_sources(rep, slugdir, slug, text, source_name)
    check_empty_dirs(rep, slugdir)


def check_recipe_body(rep: Report, slugdir: Path, text: str) -> None:
    """Recipe-only rules from recipe-content.instructions.md."""
    where = f"{rel(slugdir)}/recipe.md"

    for heading in REQUIRED_RECIPE_HEADINGS:
        if heading not in text:
            rep.error(where, f"missing required `{heading}` section")

    # Metadata bullets: "- **Key:** value". Flag unknown keys and empty values.
    for key, value in re.findall(r"^- \*\*([^:*]+):\*\*(.*)$", text, re.M):
        if key not in KNOWN_META_KEYS:
            rep.warn(where, f"unrecognized metadata key **{key}:** — typo, or add it to KNOWN_META_KEYS")
        elif not value.strip():
            rep.warn(where, f"metadata key **{key}:** has no value; omit the line instead")
        elif key == "Image position" and value.strip().lower() not in IMAGE_POSITIONS:
            rep.error(
                where,
                f"Image position {value.strip()!r} is not one of "
                f"{', '.join(sorted(IMAGE_POSITIONS))} — the renderer would ignore it and crop by the detected dish",
            )

    directions = section_body(text, "## Directions")
    if directions is not None:
        check_directions(rep, where, directions)


def section_body(text: str, heading: str) -> str | None:
    """Text between `heading` and the next `## ` heading (or end of document)."""
    match = re.search(rf"^{re.escape(heading)}\s*$", text, re.M)
    if not match:
        return None
    rest = text[match.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def check_directions(rep: Report, where: str, body: str) -> None:
    """Directions must be one sequentially numbered list with no bold subheads."""
    numbers = [int(n) for n in re.findall(r"^\s*(\d+)\.\s", body, re.M)]
    if not numbers:
        if body.strip():
            rep.error(where, "Directions section has no numbered steps")
        return
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        rep.error(
            where,
            f"Directions are not one sequentially numbered list — got {numbers}, want {expected}",
        )

    for line in body.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\*\*[^*]+:?\*\*:?", stripped):
            rep.error(
                where,
                f"bold subhead {stripped!r} inside Directions — fold phase names into step text",
            )


def check_images(rep: Report, slugdir: Path, slug: str, text: str) -> None:
    where = rel(slugdir)
    images = slugdir / "images"
    canonical = images / f"{slug}.jpg"

    if images.is_dir():
        derived = {f"{slug}-{k}.jpg" for k in DERIVED_SUFFIXES}
        for f in sorted(p for p in images.iterdir() if p.is_file()):
            if f.name == f"{slug}.jpg" or f.name in derived:
                continue
            rep.warn(
                f"{where}/images",
                f"{f.name} is neither the canonical {slug}.jpg nor a derived crop — "
                "the renderer will never reference it",
            )

    # Every image link in the markdown must resolve relative to the entry folder.
    for link in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        if link.startswith(("http://", "https://", "data:")):
            continue
        target = (slugdir / link).resolve()
        if not target.exists():
            rep.error(f"{where}/*.md", f"image link {link!r} does not resolve")
        elif link.rsplit("/", 1)[-1] != f"{slug}.jpg":
            rep.warn(
                f"{where}/*.md",
                f"image link {link!r} is not the canonical images/{slug}.jpg — "
                "derived crops are chosen by the renderer, not linked by hand",
            )

    if canonical.exists() and "![" not in text:
        rep.warn(where, f"has images/{slug}.jpg but the markdown has no image link")


def check_sources(rep: Report, slugdir: Path, slug: str, text: str, source_name: str) -> None:
    where = rel(slugdir)
    source = slugdir / "sources" / source_name
    linked = f"sources/{source_name}" in text

    if source.exists() and not linked:
        rep.warn(where, f"has sources/{source_name} but the markdown does not link to it")
    if linked and not source.exists():
        rep.error(where, f"links to sources/{source_name}, which does not exist")


ENTRY_SUBDIRS = ("images", "sources", "prompts", "extras")


def check_empty_dirs(rep: Report, slugdir: Path) -> None:
    for d in sorted(p for p in slugdir.iterdir() if p.is_dir()):
        if d.name not in ENTRY_SUBDIRS:
            rep.error(
                rel(d),
                f"unexpected subdirectory — an entry holds only {', '.join(ENTRY_SUBDIRS)}/",
            )
        elif not any(d.iterdir()):
            rep.error(rel(d), "empty directory — remove it (see AGENTS.md)")


# -------------------------------------------------------------------- manifest


CONFIG_REL = "book/book.yaml"


def check_layouts(rep: Report, known: set[tuple[str, str]]) -> None:
    """The `layouts:` list in book.yaml — curated archetype assignments.

    render.py ignores a row that matches no entry, so a stale one survives
    a rename indefinitely while the book keeps building.
    """
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(render.CONFIG.layouts):
        chapter, slug = row["chapter"], row["slug"]
        key = (chapter, slug)
        where = f"{CONFIG_REL}: layouts[{i}] ({chapter}/{slug})"

        if key in seen:
            rep.error(where, "duplicate layout row")
        seen.add(key)

        if key not in known:
            rep.error(where, "no matching entry folder — stale after a rename or removal")

        if row["archetype"] not in render.RENDERERS:
            rep.error(
                where,
                f"unknown archetype {row['archetype']!r}; "
                f"known: {', '.join(sorted(render.RENDERERS))}",
            )

        spec = row.get("spec")
        if spec and not (ROOT / str(spec)).exists():
            rep.error(where, f"spec path does not exist: {spec}")


def check_config(rep: Report, content_cats: set[str]) -> None:
    """book.yaml's chapter list against what is actually on disk."""
    for chapter in render.CONFIG.chapters:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", chapter.accent):
            rep.error(
                f"{CONFIG_REL}: chapters",
                f"{chapter.name!r} accent {chapter.accent!r} is not a #RRGGBB color",
            )

        # A generated chapter has no folder; check_generated_pages rejects one.
        if chapter.generated:
            continue
        folder = BOOK / chapter.base / chapter.name
        if not folder.is_dir():
            rep.error(
                f"{CONFIG_REL}: chapters",
                f"{chapter.name!r} is declared kind={chapter.kind!r} but "
                f"{rel(folder)}/ does not exist",
            )
        elif not entry_folders(folder):
            has_page = (BOOK / "sections" / chapter.name / "page.md").exists()
            if not has_page:
                rep.warn(
                    f"{CONFIG_REL}: chapters",
                    f"{chapter.name!r} has no entries and no page.md — it renders nothing",
                )
            elif chapter.divider:
                # A chapter without a divider is its page.md (a dedication);
                # one with a divider prints an opener for entries that never come.
                rep.warn(
                    f"{CONFIG_REL}: chapters",
                    f"{chapter.name!r} has no entries — it prints an opening page and "
                    "nothing after it; add an entry or remove the chapter from book.yaml",
                )

    # A folder with no config block still renders, but at the end of the book in
    # the default color — check_structure warns about it. Cover art is
    # checked here because nothing else reads it until a cover build.
    photo = render.CONFIG.cover.get("photo")
    if photo and not (BOOK / "recipes" / str(photo)).exists():
        rep.error(f"{CONFIG_REL}: cover", f"photo does not exist: book/recipes/{photo}")

    # Prose belongs in markdown, so book.yaml must not grow content fields back.
    for key in ("back_blurb", "back_signoff"):
        if key in render.CONFIG.cover:
            rep.error(
                f"{CONFIG_REL}: cover",
                f"{key} is prose and belongs in book/cover.md, not in the config",
            )


def check_config_keys(rep: Report) -> None:
    """Top-level keys the engine does not read, such as a removed `print:` block."""
    raw = yaml.safe_load(render.BOOK_ROOT.config_path.read_text(encoding="utf-8")) or {}
    for key in raw:
        if key not in config.TOP_LEVEL_KEYS:
            rep.warn(
                CONFIG_REL,
                f"unknown key {key!r} is ignored; the engine reads "
                f"{', '.join(config.TOP_LEVEL_KEYS)}",
            )


# What `cookbook init` writes into every page and setting it cannot fill in.
PLACEHOLDER = "TODO"
PLACEHOLDER_HINT = "placeholder text from `cookbook init` — replace it before printing"


def check_placeholders(rep: Report) -> None:
    """Leftover init placeholders: in any markdown under book/ (cover.md and the
    chapter, dedication, and closing pages included) and in book.yaml's values.
    Nothing else stops them: they render like any other words."""
    for path in sorted(BOOK.rglob("*.md")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PLACEHOLDER in line:
                rep.error(f"{rel(path)}:{n}", PLACEHOLDER_HINT)

    def walk(node: yaml.Node | None, key: str) -> None:
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                walk(v, f"{key}.{k.value}" if key else str(k.value))
        elif isinstance(node, yaml.SequenceNode):
            for i, v in enumerate(node.value):
                walk(v, f"{key}[{i}]")
        elif isinstance(node, yaml.ScalarNode) and PLACEHOLDER in node.value:
            rep.error(f"{CONFIG_REL}:{node.start_mark.line + 1}", f"{key} is {PLACEHOLDER_HINT}")

    walk(yaml.compose(render.BOOK_ROOT.config_path.read_text(encoding="utf-8")), "")


def check_cover_copy(rep: Report) -> None:
    """book/cover.md — the back-cover prose the cover build reads."""
    path = BOOK / "cover.md"
    if not path.exists():
        rep.warn(rel(path), "no cover copy — the back cover will print empty")
        return
    blurb, signoff = config.load_cover_copy(render.BOOK_ROOT)
    if not blurb:
        rep.warn(rel(path), "no blurb paragraph found — the back cover will print empty")
    if not signoff:
        rep.warn(rel(path), "no *italic* sign-off line found")


def check_generated_pages(rep: Report) -> None:
    """A generated page must not also exist as markdown.

    The title page, contents, contributors, and index are built by the renderer
    from book.yaml and the finished page order; they belong to no folder, so one
    with any of these names anywhere in the book is an authored duplicate.
    Authoring one would not override the generated page: a chapter folder by
    that name is never read, and an entry by that name prints as a second copy.
    Either way the authored words drift from the generated ones.
    """
    for slug, source in config.GENERATED_PAGES.items():
        for folder in sorted(BOOK.glob(f"*/*/{slug}")) + sorted(BOOK.glob(f"*/{slug}")):
            rep.error(
                rel(folder),
                f"this page is generated from {source} — delete the folder; an "
                "authored copy never replaces the generated page",
            )


def check_divider_titles(rep: Report) -> None:
    """A chapter's page holds its prose and nothing else.

    book/sections/{chapter}/page.md is one file doing one job: the page that
    belongs to the chapter rather than to any entry. With `divider: true` it
    opens the section; with `divider: false` it IS the chapter, as a dedication
    or a closing message is. Either way its heading is the chapter's label from
    book.yaml, which is also what the table of contents prints — so an H1 here
    would be a second copy of a name that already has a home.
    """
    for chapter in render.CONFIG.chapters:
        path = BOOK / "sections" / chapter.name / "page.md"
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8")
        h1 = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), None)
        if h1 is not None:
            rep.error(
                rel(path),
                f"has an H1 ({h1!r}); a chapter page takes its heading from the chapter's "
                f"`label` in {CONFIG_REL}. Delete the heading and keep only the prose",
            )
        if not text.strip():
            rep.error(
                rel(path),
                "is empty. A chapter's opening page renders because book.yaml gives the "
                "chapter divider: true, not because this file exists — delete it, or write "
                "the prose",
            )


# ------------------------------------------------------------------ structure


def check_structure(rep: Report, recipe_cats: set[str], section_cats: set[str]) -> None:
    # Every group of entries is a chapter, front and back matter included — the
    # chapters list in book.yaml is the whole book, in order.
    content_cats = recipe_cats | section_cats

    # A category present in two bases is ambiguous: base_for() silently picks one
    # and the other half of the chapter never renders, while the build succeeds.
    for cat in sorted(recipe_cats & section_cats):
        rep.error(
            "book/",
            f"category {cat!r} exists in BOTH book/recipes/ and book/sections/ — "
            "a category belongs to exactly one; entries in the other are dropped silently",
        )

    for cat in sorted(content_cats):
        if cat not in render.BOOK_STRUCTURE:
            rep.warn(
                f"book/{'recipes' if cat in recipe_cats else 'sections'}",
                f"category {cat!r} is not in the chapters list in {CONFIG_REL} — "
                "it renders at the end of the book",
            )

    # A chapter's `kind` decides its base; entries in the other one are dropped.
    for cat in sorted(recipe_cats):
        ch = render.CONFIG.by_name.get(cat)
        if ch and ch.kind == "prose":
            rep.error(
                f"book/recipes/{cat}",
                f"{cat!r} is kind: prose in {CONFIG_REL} — its entries belong under book/sections/",
            )
    for cat in sorted(section_cats):
        ch = render.CONFIG.by_name.get(cat)
        if ch and ch.kind == "recipes":
            rep.error(
                f"book/sections/{cat}",
                f"{cat!r} is kind: recipes in {CONFIG_REL} — its entries belong under "
                "book/recipes/ (only its page.md lives here)",
            )

    # A one-page chapter (divider: false, with a page of its own) renders that
    # page in the flow and nothing else, so entries beneath it would vanish.
    for page in chapter_pages():
        cat = page.parent.name
        if cat in render.DIVIDER_CATEGORIES:
            continue
        entries = [p.name for p in entry_folders(page.parent)]
        if entries:
            rep.error(
                rel(page.parent),
                f"{cat!r} is divider: false with a page of its own, so it is a one-page "
                f"chapter — but it also holds entries ({', '.join(entries)}), which never render",
            )

    # book/sections/ is the section registry: one folder per section of the book,
    # holding that section's own material. A folder book.yaml does not name is
    # either stale or a chapter not yet configured; one holding entries was
    # already reported above.
    registry = BOOK / "sections"
    if registry.is_dir():
        for d in sorted(p for p in registry.iterdir() if p.is_dir()):
            if d.name in render.BOOK_STRUCTURE or d.name in content_cats:
                continue
            if (d / "page.md").exists():
                rep.warn(
                    rel(d),
                    f"{d.name!r} is not in the chapters list in {CONFIG_REL} — its "
                    "page.md renders as a one-page chapter at the end of the book",
                )
            else:
                rep.warn(
                    rel(d),
                    f"{d.name!r} is not a section of the book — stale after a rename, "
                    f"or missing from {CONFIG_REL}",
                )

    missing = sorted(
        cat for cat in set(render.DIVIDER_CATEGORIES) & content_cats
        if not (registry / cat / "page.md").exists()
    )
    if missing:
        rep.warn(
            "book/",
            f"{len(missing)} chapter(s) open with only their name and no page of "
            f"their own: {', '.join(missing)}",
        )

    # The table of contents is synthetic; check_generated_pages catches a folder
    # by its generated name, and this catches the obvious shorthand for one.
    for stray in BOOK.rglob("*"):
        if stray.is_dir() and stray.name == "toc":
            rep.error(rel(stray), "the table of contents is generated; never author one")

    # `pinned` holds entries at the FRONT only, so a partial list is normal and
    # not worth flagging. What it cannot do is hold one at the BACK — which is
    # why book.yaml warns that back matter's closing message is last only while
    # it is the sole entry there.
    #
    # A pinned slug naming nothing is a dead pin, silently ignored at build time.
    for cat, slugs in render.PINNED_ENTRIES.items():
        base = BOOK / render.base_for(cat) / cat
        for slug in slugs:
            if not (base / slug).is_dir():
                rep.warn(
                    CONFIG_REL,
                    f"chapters[{cat}].pinned lists {slug!r}, which no longer exists",
                )


# ---------------------------------------------------------------------- extras


# Smallest long edge, in pixels, for a keepsake to print sharply where it lands:
# roughly 200 ppi at its printed size — an inset about 2.3in tall and up to
# ~3.5in wide, or a keepsake page item up to ~7.4in across.
EXTRA_MIN_PX = {"inset": 700, "page": 1500}


def check_extras(rep: Report) -> None:
    """extras/ folders: the curated keepsakes (card scans, photos, letters) of an
    entry or a chapter. Only what extras/extras.md lists prints; everything else
    is kept safely and reported here so nobody is surprised it is missing."""
    from PIL import Image

    # Where each listed item lands, decided exactly as the renderer decides it.
    pages = render.place_extras(render.assemble_recipes())
    placement = {x.path: ("page" if r.is_keepsake else "inset") for r in pages for x in r.extras}
    for r in pages:
        if r.extras_placement == "inset" and not r.is_keepsake and not r.extras \
                and render.load_extras(r.folder):
            rep.warn(
                f"{CONFIG_REL}: layouts ({r.category}/{r.slug})",
                f"extras: inset is ignored — a {r.archetype} page takes no inset "
                f"(or more than {render.INSET_MAX_ITEMS} items); they print on a keepsake page",
            )
    for row in render.CONFIG.layouts:
        if "extras" in row:
            folder = BOOK / render.base_for(row["chapter"]) / row["chapter"] / row["slug"]
            if not (folder / render.EXTRAS_DIR).is_dir():
                rep.warn(
                    f"{CONFIG_REL}: layouts ({row['chapter']}/{row['slug']})",
                    "sets extras: but the entry has no extras/ folder",
                )

    for d in sorted(p for p in BOOK.rglob(render.EXTRAS_DIR) if p.is_dir()):
        where = rel(d)
        owner = d.parent
        is_entry = (owner / "recipe.md").exists() or (owner / "page.md").exists()
        if not (is_entry or owner.parent == BOOK / "sections"):
            rep.error(
                where,
                "never read — an entry's extras/ sits in its entry folder, a chapter's "
                "in book/sections/{chapter}/extras/",
            )
            continue

        files = sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith("."))
        listing = d / render.EXTRAS_LIST
        if not files:
            rep.error(where, "empty directory — remove it (see AGENTS.md)")
            continue
        if not listing.exists():
            rep.warn(
                where,
                f"no {render.EXTRAS_LIST}, so nothing here prints — list each item to print "
                f"as an image line, e.g. ![Caption](file.jpg)",
            )
            continue

        listed = render.extras_listing(owner)
        if not listed:
            rep.error(f"{where}/{render.EXTRAS_LIST}", "lists no images — add ![Caption](file.jpg) lines")
        names = [name for name, _ in listed]
        for name in sorted({n for n in names if names.count(n) > 1}):
            rep.warn(f"{where}/{render.EXTRAS_LIST}", f"lists {name} more than once — it prints twice")
        for name, caption in listed:
            path = d / name
            if not path.is_file():
                rep.error(f"{where}/{render.EXTRAS_LIST}", f"lists {name}, which does not exist")
                continue
            if path.suffix.lower() not in render.EXTRA_SUFFIXES:
                rep.error(
                    f"{where}/{render.EXTRAS_LIST}",
                    f"{name} is not a .jpg or .png — convert it, or it never prints",
                )
                continue
            if not caption:
                rep.warn(f"{where}/{render.EXTRAS_LIST}", f"{name} has no caption — say who, what, and when")
            spot = placement.get(path)
            if spot is None:
                rep.warn(
                    f"{where}/{name}",
                    "listed but not printed — its chapter has no page of its own to carry it",
                )
                continue
            with Image.open(path) as img:
                long_edge = max(img.size)
                alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
            if long_edge < EXTRA_MIN_PX[spot]:
                rep.warn(
                    f"{where}/{name}",
                    f"{img.size[0]}x{img.size[1]}px is low resolution for a "
                    f"{'keepsake page' if spot == 'page' else 'page inset'} — want a long edge "
                    f"of {EXTRA_MIN_PX[spot]}px or more; rescan at 300-600 dpi",
                )
            if alpha:
                rep.warn(
                    f"{where}/{name}",
                    "has transparency, which print preflight flags — save it as a flat .jpg",
                )

        listed_names = {(d / n).resolve() for n in names}
        for f in files:
            if f.name != render.EXTRAS_LIST and f.resolve() not in listed_names:
                rep.warn(f"{where}/{f.name}", f"not listed in {render.EXTRAS_LIST} — not printed")


def collect() -> Report:
    """Every structural problem in the active book, unprinted."""
    rep = Report()

    recipes = entry_dirs(BOOK / "recipes")     # recipe chapters
    sections = entry_dirs(BOOK / "sections")   # prose groups, incl. front/back matter

    for _, slugdir in recipes:
        check_entry(rep, slugdir, "recipe.md", "recipe-original.md")
        md = slugdir / "recipe.md"
        if md.exists():
            check_recipe_body(rep, slugdir, md.read_text(encoding="utf-8"))

    for _, slugdir in sections:
        check_entry(rep, slugdir, "page.md", "page-original.md")

    known = {(c, d.name) for c, d in recipes} | {(c, d.name) for c, d in sections}
    check_layouts(rep, known)
    check_config(rep, {c for c, _ in recipes} | {c for c, _ in sections})
    check_cover_copy(rep)
    check_config_keys(rep)
    check_placeholders(rep)
    check_divider_titles(rep)
    check_generated_pages(rep)
    check_structure(rep, {c for c, _ in recipes}, {c for c, _ in sections})
    check_extras(rep)
    return rep


def main(errors_only: bool = False, quiet: bool = False) -> int:
    rep = collect()
    recipes = entry_dirs(BOOK / "recipes")
    sections = entry_dirs(BOOK / "sections")
    chapter_page_files = chapter_pages()

    if not quiet:
        for line in rep.errors:
            print(f"ERROR  {line}")
        if not errors_only:
            for line in rep.warnings:
                print(f"WARN   {line}")
        counted = (f"{len(recipes)} recipes, {len(sections)} section entries, "
                   f"{len(chapter_page_files)} chapter pages")
        print(
            f"\n{counted} — {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)"
            if (rep.errors or rep.warnings)
            else f"\n{counted} — clean"
        )

    return 0 if rep.ok else 1
