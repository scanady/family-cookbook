"""Render a draft cookbook from the layout manifest.

Reads book/book.yaml, and for each recipe that has an assigned
layout archetype, renders an 8x11in print-CSS page from the recipe markdown
and its image. Output: draft/cookbook-draft.html — open in a browser and
Print -> Save as PDF for a visual draft.

Images are referenced via relative paths so the HTML works when opened
directly from the filesystem (file://) without a web server.

This renderer *implements* the archetypes described in the
design-visual-cookbook-page-layout skill's references/ (layout-catalog.md
and design-system.md). book.yaml assigns an archetype and zone to an entry, or
the build picks one; this module turns that assignment into pixels.
"""
from __future__ import annotations

import base64
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Callable, NamedTuple

from PIL import Image, ImageDraw, ImageFilter, ImageStat

from . import config
from .lulu import LULU_HARDCOVER_MIN_PAGES, lulu_inside_margin

# The book this run lays out, activated by the CLI from --book.
BOOK_ROOT = config.active_root()
ROOT = BOOK_ROOT.path
BOOK = BOOK_ROOT.book                    # all cookbook content lives here
BOOK_REL = "../book"                     # same, relative to OUTPUT's directory
OUTPUT = BOOK_ROOT.draft / "cookbook-draft.html"
FONT_DIR = resources.files(__package__) / "fonts"

# book/book.yaml holds the book's structure, style, and curated layouts.
CONFIG = config.load_or_exit(BOOK_ROOT)

# Real design-system typefaces (embedded so the draft is self-contained).
# Variable fonts: one file spans the whole weight axis.
FONT_FACES = [
    ("Playfair Display", "normal", "400 900", "PlayfairDisplay.ttf"),
    ("Playfair Display", "italic", "400 900", "PlayfairDisplay-Italic.ttf"),
    ("Source Sans 3", "normal", "200 900", "SourceSans3.ttf"),
    ("Source Sans 3", "italic", "200 900", "SourceSans3-Italic.ttf"),
]

# `--only slug1,slug2` renders just those recipes (at their real book layout)
# for focused visual inspection of specific pages. Set by main().
ONLY: set[str] = set()

# `--print` switches to press-ready geometry for Lulu US Letter (8.5 x 11 trim):
#   - page box grows to 8.75 x 11.25 in (trim + 0.125 in bleed on every side)
#   - the paper background and Hero photos fill that whole box, so nothing trims
#     to a white sliver
#   - the binding gutter is mirrored (inner edge) by recto/verso
#   - the folio (page number) sits FOLIO_IN above the trim, inside Lulu's 0.5 in
#     safety zone; the text block keeps the same margins from the trim as on screen
# Without it, the on-screen 8 x 11 draft is produced. Set by main().
PRINT = False

# Structure and style come from book/book.yaml. index.py reads this name.
CATEGORY_LABELS = CONFIG.labels

# Every group of entries lives in one of two bases, chosen by entry format:
#
#   book/recipes/{name}/{slug}/recipe.md   food only
#   book/sections/{name}/{slug}/page.md    prose — including front and back
#                                          matter, which are sections too
#
# What makes a group a CHAPTER rather than structural furniture is book.yaml,
# not its location: a chapter appears in the `chapters:` list, takes a place in
# the running order, an accent, and a divider. Front and back matter do not.
#
# book/sections/{name}/ is the SECTION REGISTRY: one folder per chapter of the
# book, holding that chapter's own material. Every chapter has a folder here,
# including recipe chapters whose entries live under book/recipes/.
#
#   book/sections/{chapter}/page.md          the CHAPTER's own page
#   book/sections/{chapter}/{slug}/page.md   a prose entry
#   book/recipes/{chapter}/{slug}/recipe.md  a recipe entry
#
# A chapter's page.md is one file doing one job: the page that belongs to the
# chapter itself rather than to any entry. `divider: true` renders it as the
# section opener before the entries; `divider: false` renders it as a page in
# the flow, which is what a dedication or a closing message is. Its heading
# comes from the chapter's `label`, so it carries no H1 of its own.
#
# A chapter declares its base in book/book.yaml via `kind` (recipes | prose). An
# unconfigured folder still resolves from the tree, so a chapter added before it
# has a config block renders at the end of the book rather than vanishing.
base_for = CONFIG.base_for
TOC_CATEGORIES = set(CONFIG.toc_categories)


@dataclass(frozen=True)
class Extra:
    """One printable keepsake listed in an extras/extras.md: a card scan, a family
    photo, a letter. `path` is absolute; `caption` is the image line's alt text;
    `aspect` is width / height, which sizes it on the page without a letterbox."""
    path: Path
    caption: str
    aspect: float


@dataclass
class Recipe:
    category: str
    slug: str
    archetype: str
    zone: str
    title: str = ""
    attribution: str = ""
    chips: list[tuple[str, str]] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)  # plain items; subheads prefixed "## "
    directions: list[str] = field(default_factory=list)   # cleaned, renumbered at render
    prose: list[str] = field(default_factory=list)        # loose body paragraphs (non-recipe items)
    notes: list[str] = field(default_factory=list)
    original_text: str = ""
    img_position: str = ""  # `Image position` override; empty = follow the detected subject
    # Who chose the archetype: "curated" (a `layouts:` row in book.yaml), "fixed"
    # (the page's kind always takes it: generated pages, dividers, keepsakes), or
    # "auto" (assigned by assign_section()).
    origin: str = "auto"
    base: str = ""  # "recipes" | "sections"; stamped by enumerate_recipes()
    is_divider: bool = False  # section-divider page; slug names the category it precedes
    is_blank: bool = False  # intentional blank inserted to force a divider onto a recto
    is_generated: bool = False  # a `kind: generated` chapter's leaf (title, contents, contributors, index): no markdown
    is_chapter_page: bool = False  # a one-page chapter: its page.md sits at the chapter root
    is_spread_photo: bool = False  # the verso photo leaf of a Two-Page Spread (see expand_two_page)
    is_spread_cont: bool = False  # the recto (continuation) leaf of a Recipe Spread (see expand_two_page)
    is_prose_cont: bool = False  # the continuation leaf of a prose page too long for one (see expand_two_page)
    is_keepsake: bool = False  # a keepsake leaf printed after its entry/chapter (see place_extras)
    extras: list[Extra] = field(default_factory=list)  # set by place_extras(): an inset here, or this keepsake leaf's items
    extras_placement: str = ""  # "inset" | "page" from the entry's layouts row; "" = decided by room
    page_number: int = 0  # 1-indexed, stamped by build() once the final page order is known
    columns: list[list[Row]] = field(default_factory=list)  # a reference leaf's rows, one list per column (see paginate)

    @property
    def is_page(self) -> bool:
        """True when the entry is prose (page.md) rather than a recipe."""
        return self.is_divider or (self.base or base_for(self.category)) != "recipes"

    @property
    def md_filename(self) -> str:
        return "page.md" if self.is_page else "recipe.md"

    @property
    def original_filename(self) -> str:
        return "page-original.md" if self.is_page else "recipe-original.md"

    @property
    def has_image(self) -> bool:
        return (self.folder / "images" / f"{self.slug}.jpg").exists()

    @property
    def accent(self) -> str:
        # Dividers borrow the accent of the section they introduce (slug names it).
        key = self.slug if self.is_divider else self.category
        return CONFIG.accents.get(key, CONFIG.default_accent)

    @property
    def folder(self) -> Path:
        # A divider's slug names the section it opens; its material lives in that
        # section's registry folder, whatever base holds the section's entries.
        if self.is_divider:
            return BOOK / "sections" / self.slug
        # A chapter's own page lives in the section registry, whichever base
        # holds its entries. The {slug} level separates multiple entries; a page
        # belonging to the chapter itself does not need one.
        if self.is_chapter_page:
            return BOOK / "sections" / self.category
        return BOOK / (self.base or base_for(self.category)) / self.category / self.slug

    @property
    def md_path(self) -> Path:
        """The markdown backing this page, if any.

        A divider's message is book/sections/{name}/page.md — with the rest of
        that section's definition, not with its entries. That is what lets the
        entries be reorganized without touching how the section is described.
        """
        if self.is_divider or self.is_chapter_page:
            return self.folder / "page.md"
        return self.folder / self.md_filename


# --------------------------------------------------------------------------- parsing


def parse_manifest() -> list[Recipe]:
    """Curated layout assignments from book/book.yaml's `layouts:` list.

    Entries absent from it are auto-assigned an archetype at build time.
    """
    return [
        Recipe(
            category=row["chapter"],
            slug=row["slug"],
            archetype=row["archetype"],
            zone=str(row.get("zone", "")),
            extras_placement=str(row.get("extras", "")),
        )
        for row in CONFIG.layouts
    ]


# Page geometry, in inches. The press build's page box is Lulu's 8.5 x 11 in
# US Letter trim plus PRINT_BLEED_IN on every side; the screen draft is an
# 8 x 11 in trim with no bleed. Both set the text block the same distance from
# the trim: cookbook margins, wider than Lulu's 0.5 in safety minimum. MARGIN_IN
# at the top, the outside edge, and the inside (gutter) edge; a deeper
# MARGIN_BOTTOM_IN, so the folio, FOLIO_IN above the trim and inside Lulu's
# safety zone, sits in clear paper below the last line of text. Full-bleed
# photographs ignore the margins and run through the bleed.
PRINT_BLEED_IN = 0.125
PRINT_PAGE_W_IN, PRINT_PAGE_H_IN = 8.75, 11.25
MARGIN_IN = 0.75
MARGIN_BOTTOM_IN = 0.875
FOLIO_IN = 0.5

# The print build's inside margin, measured from the trim. Lulu's recommended
# margin grows with the page count (lulu.lulu_inside_margin); main() warns when
# the page count needs more than this.
PRINT_INSIDE_MARGIN_IN = MARGIN_IN


def mode_vars_css() -> str:
    """Emit the @page rule and the CSS custom properties that size every page.

    Both builds mirror the gutter by recto/verso, so the screen draft reads as
    the same spreads as the book, and both set the text block MARGIN_IN /
    MARGIN_BOTTOM_IN from the trim. Padding = bleed + margin: the press build's
    page box (PRINT_PAGE_W_IN x PRINT_PAGE_H_IN) adds PRINT_BLEED_IN on every
    side; the screen draft's 8 x 11 in page is the trim itself."""
    bleed = PRINT_BLEED_IN if PRINT else 0.0
    pw, ph = (PRINT_PAGE_W_IN, PRINT_PAGE_H_IN) if PRINT else (8.0, 11.0)
    pt = outer = bleed + MARGIN_IN
    inner = bleed + (PRINT_INSIDE_MARGIN_IN if PRINT else MARGIN_IN)
    pb = bleed + MARGIN_BOTTOM_IN
    pnum_bottom = bleed + FOLIO_IN
    # Print insurance: square image corners. A rounded-corner clip can register as
    # a transparency region in preflight; 3pt is visually negligible to drop.
    extra = ".img,.photo{border-radius:0;}" if PRINT else ""
    return (
        f"@page{{size:{pw}in {ph}in;margin:0;}}"
        f":root{{--page-w:{pw}in;--page-h:{ph}in;--pad-t:{pt}in;--pad-b:{pb}in;"
        f"--pad-outer:{outer}in;--pad-inner:{inner}in;--pnum-bottom:{pnum_bottom}in;"
        f"--band-min:{BAND_MIN_IN}in;--band-max:{BAND_MAX_IN}in;"
        f"--hero-min:{HERO_MIN_IN}in;--hero-max:{HERO_MAX_IN}in;}}"
        f"{extra}"
    )


def font_face_css() -> str:
    faces = []
    for family, style, weight, filename in FONT_FACES:
        path = FONT_DIR / filename
        if not path.is_file():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';font-style:{style};"
            f"font-weight:{weight};font-display:swap;"
            f"src:url(data:font/ttf;base64,{b64}) format('truetype');}}"
        )
    return "".join(faces)


def parse_recipe(recipe: Recipe) -> None:
    path = recipe.md_path
    if (recipe.is_divider or recipe.is_chapter_page) and not path.exists():
        return  # divider with no message: title alone, taken from the config
    md = path.read_text(encoding="utf-8")
    lines = md.splitlines()

    title_idx = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    recipe.title = lines[title_idx][2:].strip() if title_idx is not None else "Untitled"

    def is_italic_line(s: str) -> bool:
        return len(s) > 2 and s.startswith("*") and s.endswith("*") and not (
            s.startswith("**") or s.endswith("**"))

    # The attribution has one slot: directly under an entry's H1. A chapter's own
    # page has no H1, so it lifts one only when the whole page is a single italic
    # line — a divider message, set under the chapter label. An italic line
    # anywhere else (a sign-off, a signature) stays in the body where it was written.
    nonblank = [i for i, l in enumerate(lines) if l.strip()]
    if title_idx is not None:
        candidates = [i for i in nonblank if i > title_idx][:1]
    else:
        candidates = nonblank if len(nonblank) == 1 else []
    attr_idx = next((i for i in candidates if is_italic_line(lines[i].strip())), None)
    recipe.attribution = lines[attr_idx].strip().strip("*").strip() if attr_idx is not None else ""

    for l in lines:
        m = re.match(r"-\s+\*\*(.+?):\*\*\s+(.+)", l)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "Image position":
                recipe.img_position = val.lower()
            elif val.lower() not in {"not specified", "not applicable"}:
                recipe.chips.append((key, val))

    def is_noise(text: str) -> bool:
        # bogus fragments from bad source splits: bare numbers, empty, lone punctuation
        return not text or bool(re.fullmatch(r"[\d\.\)\*\s]+", text))

    section = "prose"  # loose body before any heading (non-recipe items)
    for i, l in enumerate(lines):
        if i == attr_idx:
            continue  # already surfaced as the page attribution
        s = l.strip()
        if s.startswith("# ") or s.startswith("!["):
            continue  # title / image already handled
        if re.match(r"-\s+\*\*.+?:\*\*", s):
            continue  # metadata bullet already handled
        if s.startswith("## Ingredients"):
            section = "ing"; continue
        if s.startswith("## Directions"):
            section = "dir"; continue
        if s.startswith("## Notes"):
            section = "notes"; continue
        if s.startswith("## "):
            section = None; continue
        if s.startswith("[View the original"):
            section = None; continue  # drop the source-link line; not rendered
        if not s:
            continue
        if section == "ing":
            sub = re.match(r"\*\*(.+?):\*\*", s)
            if sub:
                recipe.ingredients.append("## " + sub.group(1).strip())
            elif s.startswith("- ") and not is_noise(s[2:].strip()):
                recipe.ingredients.append(s[2:].strip())
        elif section == "dir":
            m = re.match(r"\d+\.\s+(.+)", s)
            text = (m.group(1) if m else s).strip()
            if not is_noise(text):
                recipe.directions.append(text)
        elif section == "notes":
            text = s[2:].strip() if s.startswith("- ") else s
            if not is_noise(text):
                recipe.notes.append(text)
        elif section == "prose" and not is_noise(s):
            recipe.prose.append(s)

    original = recipe.folder / "sources" / recipe.original_filename
    if original.exists():
        block = re.search(r"```text\n(.*?)```", original.read_text(encoding="utf-8"), re.DOTALL)
        recipe.original_text = block.group(1).strip() if block else ""


# --------------------------------------------------------------------------- html pieces


def esc(text: str) -> str:
    return html.escape(text)


def md_inline(text: str) -> str:
    """Escape then convert inline **bold**/*italic* markdown that source
    prose/notes/ingredients/directions may still contain (source content isn't
    guaranteed to avoid it, unlike the title/attribution/chip fields, which
    never carry markdown emphasis)."""
    escaped = esc(text)
    escaped = re.sub(r"&lt;br\s*/?&gt;", "<br>", escaped, flags=re.IGNORECASE)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def meta_html(r: Recipe) -> str:
    """A clean cookbook meta strip: small accent label above value.

    Category is dropped (redundant with the section it lives in)."""
    items = []
    for k, v in r.chips:
        if k.lower() == "category":
            continue
        items.append(
            f'<div class="meta-item"><span class="meta-label">{esc(k)}</span>'
            f'<span class="meta-val">{esc(v)}</span></div>'
        )
    return f'<div class="meta">{"".join(items)}</div>' if items else ""


def header_html(r: Recipe, long_title: bool = False) -> str:
    cls = "title title--long" if long_title or len(r.title) > 24 else "title"
    return (
        f'<div class="header">'
        f'<h1 class="{cls}">{esc(r.title)}</h1>'
        f'<p class="attr">{esc(r.attribution)}</p>'
        f'<div class="rule"></div>'
        f"{meta_html(r)}"
        f"</div>"
    )


def ingredients_html(r: Recipe) -> str:
    if not r.ingredients:
        return ""
    items = []
    for it in r.ingredients:
        if it.startswith("## "):
            items.append(f'<li class="subhead">{esc(it[3:])}</li>')
        else:
            items.append(f"<li>{md_inline(it)}</li>")
    return (
        '<div class="block"><h2 class="sec">Ingredients</h2>'
        f'<ul class="ingredients">{"".join(items)}</ul></div>'
    )


def directions_html(r: Recipe) -> str:
    if not r.directions:
        return ""
    items = "".join(f"<li>{md_inline(t)}</li>" for t in r.directions)  # <ol> numbers sequentially
    return (
        '<div class="block"><h2 class="sec">Directions</h2>'
        f'<ol class="directions">{items}</ol></div>'
    )


def notes_html(r: Recipe) -> str:
    if not r.notes:
        return ""
    items = "".join(f"<li>{md_inline(n)}</li>" for n in r.notes)
    return (
        '<div class="block block--notes"><h2 class="sec">Notes</h2>'
        f'<ul class="notes">{items}</ul></div>'
    )


# The frame each photo-bearing archetype prints its photograph in — width and
# height in inches in the press build (mode_vars_css(): a PRINT_PAGE_W_IN x
# PRINT_PAGE_H_IN page box and a TEXT_COLUMN_IN text column) — the suffix of the crop
# `cookbook fit` cuts for it from the canonical image, and its kind:
#   bleed   full-bleed; prints the largest window, backdrop and all
#   band    a band across the text column; tightened around the dish
#   column  a tall column; tightened around the food, for standing subjects
# A band and the hero have no fixed height and no pre-cut crop: the photo takes
# the height the text leaves, within its range (BAND_MIN_IN..BAND_MAX_IN,
# HERO_MIN_IN..HERO_MAX_IN), and FIT_SCRIPT frames the canonical image in it
# once that height is known (photo_windows()). Their rows have no key and no
# height; photo_fit() judges them at the height photo_height() predicts. The
# screen draft is a narrower preview; object-fit trims a pre-cut crop there,
# centered on the dish. The Recipe Spread has no frame: its photograph takes
# whatever height the flowed text leaves (see FIT_SCRIPT), so it prints the
# canonical image and object-fit trims it.
TEXT_COLUMN_IN = PRINT_PAGE_W_IN - 2 * PRINT_BLEED_IN - PRINT_INSIDE_MARGIN_IN - MARGIN_IN
TEXT_AREA_IN = PRINT_PAGE_H_IN - 2 * PRINT_BLEED_IN - MARGIN_IN - MARGIN_BOTTOM_IN  # its height
SIDEBAR_HEADER_IN = 1.665
PHOTO_FRAMES = {
    "Two-Page Spread": ("spread", PRINT_PAGE_W_IN, PRINT_PAGE_H_IN, "bleed"),  # .img--spread: the page box, bleed included
    "Hero Full-Bleed": (None, PRINT_PAGE_W_IN, None, "bleed"),  # .photo--hero: down to the text panel
    "Half-Page Classic": (None, TEXT_COLUMN_IN, None, "band"),  # .photo--band
    # .img--sidebar: the .sidebar-row grid cell (0.85fr of the column less its
    # 18pt gap) under a one-line title block, SIDEBAR_HEADER_IN tall (measured)
    "Sidebar Portrait": ("sidebar", (TEXT_COLUMN_IN - 0.25) * 0.85 / 1.85,
                         TEXT_AREA_IN - SIDEBAR_HEADER_IN, "column"),
    "Inset Original": (None, TEXT_COLUMN_IN, None, "band"),
}
# A band's height range. Below BAND_MIN_IN a photo across the text column is a
# strip that crops every dish to a sliver; past BAND_MAX_IN (about 70% of the
# 9.75 in text area) it crowds the recipe. A recipe whose text leaves less than
# BAND_MIN_IN at full type does not take a band. The hero's photo runs from
# 5 in (half the page, the panel never taller than the picture) to 7.25 in.
BAND_MIN_IN = 3.0
BAND_MAX_IN = 6.75
HERO_MIN_IN = 5.0
HERO_MAX_IN = 7.25
PRINT_PPI = 300   # a tightened crop never prints below this
DISH_AIR = 0.3    # a tightened crop leaves this share of the dish's size as air around it
DISH_TOP_AIR = 0.08  # air above the subject's top, as a share of the window, when its foot is cut
# What a frame must show. The food (Subject.box, the detailed, edible mass) and
# the subject (Subject.extent, the food with its glass, mug, cake stand, plate,
# or pan) are judged apart: a frame may crop a vessel's side or a plate's edge,
# as food photography does, but never cuts through the subject's top — a
# glass's rim, a pint's head, a cake's crown, a bowl's rim — and never cuts the
# food. A tall subject loses its foot rather than its top.
#   - Hero, band, and spread: at least FOOD_WHOLE of the food's width and
#     height. FOOD_WHOLE is measured on the box holding 98% of the food's mass,
#     which runs past the food's visible edge: every crop audited by eye at 0.7
#     or more showed the food whole, its vessel's rim cropped at most. A band
#     is judged at the height photo_height() predicts for the recipe.
#   - Sidebar: COLUMN_FOOD of the food's width, so a wide dish is never sliced
#     down the middle, and the dish filling at least COLUMN_FILL of the
#     column's height rather than sitting at the foot of a column of backdrop.
#     A subject that passes is a standing one — a glass, a mug — and in any
#     other frame keeps STANDING_WHOLE of its silhouette, foot included.
FOOD_WHOLE = 0.7
COLUMN_FOOD = 0.9
COLUMN_FILL = 0.5
STANDING_WHOLE = 0.9
BAND_FOOD_HELD = 0.55

# `- **Image position:**` values: a manual override of where the crop window
# sits vertically, for a photo the subject detection below misjudges.
POSITION_GRAVITY = {"top": 0.0, "center": 0.5, "bottom": 1.0}


class Subject(NamedTuple):
    """Where the dish sits in a photograph, in fractions of the photo: its share
    of the subject mass in each column and each row of the analysis grid (each
    sums to 1); `box` (x0, y0, x1, y1), holding 98% of that mass — the dish's
    most detailed part, the food; `extent`, the whole subject — the food with
    its glass, mug, stand, plate, or pan; and
    `live` (y0, y1), the rows of the photo proper, between any flat padding."""
    cols: tuple[float, ...]
    rows: tuple[float, ...]
    box: tuple[float, float, float, float]
    extent: tuple[float, float, float, float]
    live: tuple[float, float]


SUBJECT_GRID = 96  # analysis columns; the rows follow the photo's aspect
# Detection takes a tenth of a second a photo, too slow to repeat on every
# build, so its results are kept in the (gitignored) build-output folder,
# keyed by the photo's size and mtime. Bump SUBJECT_VERSION whenever
# detect_subject() changes, so every photo is analyzed again.
SUBJECT_CACHE = BOOK_ROOT.draft / "photo-subjects.json"
SUBJECT_VERSION = 7
OUTLINE_EDGE = 22  # edge strength (FIND_EDGES on the blurred photo) that counts as an outline
STAND_GAP = 0.12  # how far below a dish a faintly joined foot or stand may start


@lru_cache(maxsize=None)
def _subject_cache() -> dict:
    return json.loads(SUBJECT_CACHE.read_text()) if SUBJECT_CACHE.exists() else {}


@lru_cache(maxsize=None)
def photo_subject(path: Path) -> Subject:
    """detect_subject(path), through the cache. A photo outside book/ (a
    `cookbook photo` candidate) is analyzed but not written to the cache."""
    if not path.is_relative_to(BOOK):
        return detect_subject(path)
    cache = _subject_cache()
    stat = path.stat()
    stamp = f"v{SUBJECT_VERSION} {stat.st_size} {stat.st_mtime_ns}"
    key = path.relative_to(BOOK).as_posix()
    if cache.get(key, {}).get("stamp") != stamp:
        subject = detect_subject(path)
        cache[key] = {"stamp": stamp} | {
            name: [round(v, 5) for v in values] for name, values in subject._asdict().items()}
        SUBJECT_CACHE.parent.mkdir(exist_ok=True)
        SUBJECT_CACHE.write_text(json.dumps(cache))
    return Subject(*(tuple(cache[key][name]) for name in Subject._fields))


def detect_subject(path: Path) -> Subject:
    """Find the dish in a recipe photograph.

    The photos set a dish on a plain, low-detail surface, so the dish is where
    the photo has fine detail and color: local edge density plus saturation
    above the photo's median, damped where the color matches the photo's
    border (the backdrop, a wooden table). That map is smoothed so a dish reads
    as one blob; the largest blob, with any other at least a fifth its weight
    (a side plate, a slice), is the subject. Its saliency is squared, so the
    most detailed part — the meatballs, not the bowl they sit in — carries the
    mass a crop window tries to hold. The dish's full extent — the vessel's
    plain rims and sides, which carry far less detail — is that subject grown
    through every connected cell above a much lower floor.

    Some photos sit on a canvas padded with flat color above or below them; a
    crop that crosses into the padding shows a hard seam. `live` is the band
    of rows between such padding: at least 3% of the height of rows with almost
    no tonal variation, ending at a row of full photo detail. A plain backdrop
    also has flat rows, but it fades into the scene instead of stopping."""
    with Image.open(path) as img:
        img.draft("RGB", (400, 400))  # a JPEG decodes at 1/8 scale; finer detail is linen weave
        img = img.convert("RGB")
    gray = img.convert("L")

    def spread(y: int) -> float:
        return ImageStat.Stat(gray.crop((0, y, gray.width, y + 1))).stddev[0]

    height = gray.height
    top = next(y for y in range(height) if spread(y) >= 6)                   # first row with detail
    bottom = next(y for y in range(height - 1, -1, -1) if spread(y) >= 6) + 1  # past the last
    seam_top = top >= 0.03 * height and spread(top) >= 15
    seam_bottom = bottom <= 0.97 * height and spread(bottom - 1) >= 15
    live = (top / height if seam_top else 0.0, bottom / height if seam_bottom else 1.0)
    gw, gh = SUBJECT_GRID, round(img.height * SUBJECT_GRID / img.width)
    n = gw * gh
    edges = gray.filter(ImageFilter.GaussianBlur(1)).filter(ImageFilter.FIND_EDGES)
    edges = edges.point(lambda v: max(0, v - 6) * 4)
    # FIND_EDGES rings the image's own border; that is not detail.
    ImageDraw.Draw(edges).rectangle((0, 0, edges.width - 1, edges.height - 1), outline=0, width=3)
    edge = edges.resize((gw, gh), Image.BOX).tobytes()
    sat = img.convert("HSV").getchannel("S").resize((gw, gh), Image.BOX).tobytes()
    raw = img.resize((gw, gh), Image.BOX).tobytes()
    rgb = list(zip(raw[0::3], raw[1::3], raw[2::3]))

    def quantize(c: tuple[int, int, int]) -> tuple[int, int, int]:
        return (c[0] // 12, c[1] // 12, c[2] // 12)

    # A color the photo's border also shows is backdrop: it weighs half,
    # rising to full weight 1.5 quantization steps (18 levels) away from every
    # border color, so only the near neighbors of a border color need checking.
    border = {quantize(rgb[i]) for i in range(n)
              if i % gw < 2 or i % gw >= gw - 2 or i < 2 * gw or i >= n - 2 * gw}
    near = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if a * a + b * b + c * c <= 2]
    damp: dict[tuple[int, int, int], float] = {}

    def backdrop_damp(color: tuple[int, int, int]) -> float:
        q = quantize(color)
        if q not in damp:
            d2 = min((a * a + b * b + c * c for a, b, c in near
                      if (q[0] + a, q[1] + b, q[2] + c) in border), default=None)
            damp[q] = 1.0 if d2 is None else max(0.5, 12 * d2 ** 0.5 / 18)
        return damp[q]

    median_sat = sorted(sat)[n // 2]
    sal = [(e + max(0, s - median_sat - 10)) * backdrop_damp(c) for e, s, c in zip(edge, sat, rgb)]
    blob = Image.new("L", (gw, gh))
    blob.putdata([min(255, int(v)) for v in sal])
    smooth = blob.filter(ImageFilter.BoxBlur(2)).tobytes()
    peak = sorted(smooth)[int(n * 0.99)]

    def grow(seeds: list[int], on: list[bool], seen: list[bool]) -> list[int]:
        """Every cell in `on` 4-connected to a seed, marking each in `seen`."""
        stack = [i for i in seeds if not seen[i]]
        for i in stack:
            seen[i] = True
        cells = []
        while stack:
            i = stack.pop()
            cells.append(i)
            x = i % gw
            for j in (i - 1 if x else -1, i + 1 if x < gw - 1 else -1, i - gw, i + gw):
                if 0 <= j < n and on[j] and not seen[j]:
                    seen[j] = True
                    stack.append(j)
        return cells

    on = [v > 0.3 * peak for v in smooth]
    seen = [False] * n
    blobs = [(sum(sal[i] for i in cells), cells)
             for cells in (grow([i], on, seen) for i in range(n) if on[i]) if cells]
    heaviest = max(w for w, _ in blobs)
    subject = [i for w, cells in blobs if w >= heaviest / 5 for i in cells]
    mass = [0.0] * n
    for i in subject:
        mass[i] = sal[i] ** 2

    total = sum(mass)
    cols = tuple(sum(mass[x::gw]) / total for x in range(gw))
    rows = tuple(sum(mass[y * gw:(y + 1) * gw]) / total for y in range(gh))

    def span(profile: tuple[float, ...]) -> tuple[float, float]:
        acc, lo, hi = 0.0, None, None
        for k, v in enumerate(profile):
            acc += v
            if lo is None and acc >= 0.01:
                lo = k
            if hi is None and acc >= 0.99:
                hi = k + 1
        return lo / len(profile), hi / len(profile)

    (x0, x1), (y0, y1) = span(cols), span(rows)
    whole = grow(subject, [v > 0.1 * peak for v in smooth], [False] * n)
    xs = sorted(i % gw for i in whole)
    ys = sorted(i // gw for i in whole)
    q = len(whole) // 100  # drop the outermost 1% each side: stray specks, not rims
    ex0, ey0, ex1, ey1 = xs[q] / gw, ys[q] / gh, (xs[-1 - q] + 1) / gw, (ys[-1 - q] + 1) / gh

    # Glass, a stem, a pale frosting, or a head of foam has little color or
    # texture, so the saliency map stops short of it — but its outline is a
    # crisp line. Follow the photo's outlines out from that box, bridging the
    # small breaks a thin line has, and take everything they reach as the dish.
    # A line running across most of the photo is a table edge or a wall, not
    # the dish, and is left out, as is any canvas padding.
    lw, lh = img.width // 2, img.height // 2
    line = gray.filter(ImageFilter.GaussianBlur(1)).filter(ImageFilter.FIND_EDGES)
    line = line.filter(ImageFilter.MaxFilter(3)).resize((lw, lh), Image.BOX).tobytes()
    outline = [v >= OUTLINE_EDGE for v in line]
    for y in range(lh):
        if not live[0] <= y / lh < live[1] or sum(outline[y * lw:(y + 1) * lw]) > 0.35 * lw:
            outline[y * lw:(y + 1) * lw] = [False] * lw
    for x in range(lw):
        if sum(outline[x::lw]) > 0.35 * lh:
            outline[x::lw] = [False] * lh
    reach = [(dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if dx or dy]

    def follow(seeds: list[int]) -> set[int]:
        """Every outline cell the seeds reach across breaks of up to 3 cells."""
        stack = [i for i in seeds if outline[i]]
        found = set(stack)
        while stack:
            i = stack.pop()
            x, y = i % lw, i // lw
            for dx, dy in reach:
                j = (y + dy) * lw + x + dx
                if 0 <= x + dx < lw and 0 <= y + dy < lh and outline[j] and j not in found:
                    found.add(j)
                    stack.append(j)
        return found

    def cells(x0: float, y0: float, x1: float, y1: float) -> list[int]:
        return [y * lw + x for y in range(max(0, int(y0 * lh)), min(lh, int(y1 * lh) + 1))
                for x in range(max(0, int(x0 * lw)), min(lw, int(x1 * lw) + 1))]

    seen = follow(cells(ex0, ey0, ex1, ey1))
    if seen:
        ex0 = min(ex0, min(i % lw for i in seen) / lw)
        ex1 = max(ex1, (max(i % lw for i in seen) + 1) / lw)
        ey0 = min(ey0, min(i // lw for i in seen) / lh)
        ey1 = max(ey1, (max(i // lw for i in seen) + 1) / lh)
    # A stem or a pedestal can be too faint to follow, leaving the foot or the
    # stand beneath it apart: take an outline that starts just under the dish's
    # middle third, within STAND_GAP of the height, as part of it.
    third = (ex1 - ex0) / 3
    stand = follow(cells(ex0 + third, ey1, ex1 - third, ey1 + STAND_GAP)) - seen
    if stand:
        ex0 = min(ex0, min(i % lw for i in stand) / lw)
        ex1 = max(ex1, (max(i % lw for i in stand) + 1) / lw)
        ey1 = max(ey1, (max(i // lw for i in stand) + 1) / lh)
    return Subject(cols, rows, (x0, y0, x1, y1), (ex0, ey0, ex1, ey1), live)


@lru_cache(maxsize=None)
def _running_total(profile: tuple[float, ...]) -> tuple[float, ...]:
    """The sum of `profile`'s entries before each index."""
    totals = [0.0]
    for v in profile[:-1]:
        totals.append(totals[-1] + v)
    return tuple(totals)


def _mass_between(profile: tuple[float, ...], lo: float, hi: float) -> float:
    """The share of a Subject profile's mass between fractions lo and hi of its axis."""
    n = len(profile)
    before = _running_total(profile)

    def upto(x: float) -> float:
        k = min(int(x * n), n - 1)
        return before[k] + (x * n - k) * profile[k]
    return upto(min(1.0, hi)) - upto(lo)


def subject_crop(size: tuple[int, int], frame: tuple[str, float, float, str], subject: Subject,
                 position: str = "") -> tuple[int, int, int, int]:
    """The crop of an image of `size` for `frame` (a PHOTO_FRAMES entry) —
    native resolution, never upscaled.

    A band or column frame is tightened around the dish: the smallest window of
    the frame's aspect that holds the subject's full height and the width of
    the subject (a band) or of the food (a column), with DISH_AIR around it,
    centered on it — but never so small that it prints under PRINT_PPI. Where
    even the largest window cannot hold that, or the frame is full-bleed (whose
    backdrop is part of a full-page picture), the crop is the largest window:
    only one axis is trimmed, and the window centers the subject when it fits;
    when it does not, the window holds the most of the food, centering the food
    where several placements hold as much. A vertical slide never cuts through
    the subject's top — a glass's rim, a cake's crown, a bowl's rim — so a
    subject too tall for the window gives up its foot instead. An `Image
    position` override skips all of that and pins a vertical trim to the top,
    center, or bottom. Every window lies within the photo's `live` rows, so no
    crop shows a padded canvas's seam."""
    _, fw, fh, kind = frame
    aspect = fw / fh
    w, h = size
    food, whole = subject.box, subject.extent

    # Padding is never part of the picture: every window lies within the live rows.
    live_top, live_bottom = subject.live
    live_h = (live_bottom - live_top) * h
    trim_width = w / live_h > aspect
    mw, mh = (round(live_h * aspect), round(live_h)) if trim_width else (w, round(w / aspect))
    if kind != "bleed" and not position:
        x0, x1 = (whole if kind == "band" else food)[0::2]
        y0, y1 = whole[1], whole[3]
        cw = max((x1 - x0) * w * (1 + DISH_AIR), (y1 - y0) * h * (1 + DISH_AIR) * aspect,
                 fw * PRINT_PPI)
        if cw <= mw:
            cw, ch = round(cw), round(cw / aspect)
            left = round(min(max(0.0, (x0 + x1) / 2 * w - cw / 2), w - cw))
            top = round(h * min(max(live_top, (y0 + y1) / 2 - ch / h / 2), live_bottom - ch / h))
            return (left, top, left + cw, top + ch)

    if trim_width:
        profile, length, lo, hi, axis = subject.cols, mw / w, 0.0, 1 - mw / w, 0
    else:
        profile, length, lo, hi, axis = subject.rows, mh / h, live_top, live_bottom - mh / h, 1

    if not trim_width and position in POSITION_GRAVITY:
        t = lo + (hi - lo) * POSITION_GRAVITY[position]
    else:
        if not trim_width:  # never above the subject's top, with a sliver of air
            hi = max(lo, min(hi, whole[1] - DISH_TOP_AIR * length))
        if whole[axis + 2] - whole[axis] <= length:
            t = min(max(lo, (whole[axis] + whole[axis + 2]) / 2 - length / 2), hi)
        else:
            options = [lo + (hi - lo) * k / 200 for k in range(201)]
            best = max(_mass_between(profile, t, t + length) for t in options)
            center = (food[axis] + food[axis + 2]) / 2
            t = min((t for t in options if _mass_between(profile, t, t + length) >= best - 0.005),
                    key=lambda t: abs(t + length / 2 - center))
    if trim_width:
        left, top = round(t * w), round(live_top * h)
        return (left, top, left + mw, top + mh)
    top = round(t * h)
    return (0, top, mw, top + mh)


def master_image(r: Recipe) -> Path:
    return r.folder / "images" / f"{r.slug}.jpg"


class PhotoFit(NamedTuple):
    """A recipe photo's crop for one archetype's frame: the window cut from the
    canonical image, why the frame breaks the rules above FOOD_WHOLE ("" when
    it doesn't), and how much of the food it shows (the lesser of the shares of
    the food's width and height inside the window)."""
    box: tuple[int, int, int, int]
    problem: str
    shown: float


def photo_frame(r: Recipe, archetype: str, height: float | None = None) -> tuple:
    """`archetype`'s PHOTO_FRAMES row for r, a flexible frame's height filled in:
    `height`, or the one photo_height() predicts for the recipe."""
    key, fw, fh, kind = PHOTO_FRAMES[archetype]
    return key, fw, fh if fh is not None else (height or photo_height(r, archetype)), kind


def photo_fit(r: Recipe, archetype: str, master: Path | None = None) -> PhotoFit:
    """The crop of r's photo — or of `master`, a candidate for it — for
    `archetype`'s frame, as `cookbook fit` cuts it or FIT_SCRIPT frames a
    band, judged against the frame rules above FOOD_WHOLE."""
    frame = photo_frame(r, archetype)
    master = master or master_image(r)
    with Image.open(master) as img:
        w, h = img.size
    subject = photo_subject(master)
    box = subject_crop((w, h), frame, subject, r.img_position)
    left, top, right, bottom = box
    x0, y0, x1, y1 = subject.box
    food_h = min(y1 * h, bottom) - max(y0 * h, top)
    shown = min((min(x1 * w, right) - max(x0 * w, left)) / ((x1 - x0) * w), food_h / ((y1 - y0) * h))
    if top > (subject.extent[1] + 0.01) * h:
        return PhotoFit(box, "the frame cuts through the top of the dish", shown)
    column = frame[3] == "column"
    if frame[3] == "band":
        held = _mass_between(subject.cols, left / w, right / w) * _mass_between(subject.rows, top / h, bottom / h)
        if held < BAND_FOOD_HELD:
            return PhotoFit(box, f"the band holds {held:.0%} of the food", shown)
    elif shown < (COLUMN_FOOD if column else FOOD_WHOLE):
        return PhotoFit(box, f"the frame shows {shown:.0%} of the food", shown)
    ey0, ey1 = subject.extent[1], subject.extent[3]
    silhouette = min(ey1 * h, bottom) - max(ey0 * h, top)
    if column:
        if silhouette / (bottom - top) < COLUMN_FILL:
            return PhotoFit(box, f"the dish fills {silhouette / (bottom - top):.0%} of the column's height", shown)
        return PhotoFit(box, "", shown)
    # A subject the column frames whole (above) is a standing one — a glass, a
    # mug, a tall stack — and keeps its whole silhouette, foot included.
    standing = not photo_fit(r, "Sidebar Portrait", master).problem
    if standing and silhouette / ((ey1 - ey0) * h) < STANDING_WHOLE:
        return PhotoFit(box, "the frame cuts the foot of a standing dish", shown)
    return PhotoFit(box, "", shown)


def image_file(r: Recipe) -> Path | None:
    """Prefer a layout-fitted variant for the recipe's archetype; else the base
    image. Variants are produced (for free) by `cookbook fit`; a band
    has none, FIT_SCRIPT framing the canonical image in it."""
    frame = PHOTO_FRAMES.get(r.archetype)
    if frame and frame[0]:
        variant = r.folder / "images" / f"{r.slug}-{frame[0]}.jpg"
        if variant.exists():
            return variant
    base = master_image(r)
    return base if base.exists() else None


def object_position(r: Recipe, path: Path) -> str:
    """CSS object-position that keeps the dish in view wherever object-fit trims
    the photo further — the screen draft's narrower frames, a band an inset
    shortens, the Recipe Spread's photo of whatever height the text leaves: the
    centroid of the dish's mass within the shown file (the crop, or the whole
    photo)."""
    master = master_image(r)
    subject = photo_subject(master)
    with Image.open(master) as img:
        w, h = img.size
    left, top, right, bottom = photo_fit(r, r.archetype).box if path != master else (0, 0, w, h)

    def centroid(profile: tuple[float, ...], lo: float, hi: float) -> float:
        n = len(profile)
        cells = range(int(lo * n), max(int(lo * n) + 1, min(n, round(hi * n))))
        mass = sum(profile[k] for k in cells)
        at = sum((k + 0.5) / n * profile[k] for k in cells) / mass
        return min(1.0, max(0.0, (at - lo) / (hi - lo)))

    cx = centroid(subject.cols, left / w, right / w)
    cy = (POSITION_GRAVITY[r.img_position] if r.img_position in POSITION_GRAVITY
          else centroid(subject.rows, top / h, bottom / h))
    return f"{cx:.0%} {cy:.0%}"


def image_html(r: Recipe, cls: str) -> str:
    path = image_file(r)
    if not path:
        return f'<div class="img {cls} img--placeholder">image to be generated</div>'
    src = f"{BOOK_REL}/{r.folder.relative_to(BOOK).as_posix()}/images/{path.name}"
    return (f'<img class="img {cls}" src="{esc(src)}" alt="" '
            f'style="object-position:{object_position(r, path)}">')


# The heights, in inches, photo_windows() precomputes a crop for: past both ends
# of the band's and the hero's ranges, so a photo an extras inset or
# FIT_SCRIPT's zoom leaves outside its range, or the screen draft's narrower
# page, still finds a window of nearly its own shape.
PHOTO_WINDOW_HEIGHTS = [round(2.5 + 0.1 * k, 1) for k in range(56)]


def photo_windows(r: Recipe) -> str:
    """The crops a flexible frame (a band or the hero) could show of r's photo,
    one per height in PHOTO_WINDOW_HEIGHTS, as `aspect,x0,y0,x1,y1` (fractions
    of the canonical image) joined by `;`. FIT_SCRIPT measures the photo's box
    once the text has taken its room and frames the photo with the window
    nearest its shape — the crop subject_crop() cuts for that height, so the
    page shows exactly what photo_fit() judged."""
    master = master_image(r)
    with Image.open(master) as img:
        w, h = img.size
    subject = photo_subject(master)
    windows = []
    for height in PHOTO_WINDOW_HEIGHTS:
        frame = photo_frame(r, r.archetype, height)
        x0, y0, x1, y1 = subject_crop((w, h), frame, subject, r.img_position)
        windows.append(f"{frame[1] / height:.4f},{x0 / w:.4f},{y0 / h:.4f},{x1 / w:.4f},{y1 / h:.4f}")
    return ";".join(windows)


def flex_photo_html(r: Recipe, cls: str) -> str:
    """A photo of flexible height: the canonical image in a box that takes the
    room the text leaves, framed by FIT_SCRIPT from photo_windows() once the
    box's size is known."""
    path = image_file(r)
    if not path:
        return f'<div class="img {cls} img--placeholder">image to be generated</div>'
    src = f"{BOOK_REL}/{r.folder.relative_to(BOOK).as_posix()}/images/{path.name}"
    return (f'<div class="photo {cls}" data-windows="{photo_windows(r)}">'
            f'<img src="{esc(src)}" alt=""></div>')


def prose_parts_html(lines: list[str]) -> str:
    """Loose paragraphs, with consecutive `- ` lines grouped into a real
    bullet list rather than each rendering as its own literal-dash paragraph."""
    parts = []
    bullets: list[str] = []

    def flush() -> None:
        if bullets:
            items = "".join(f"<li>{md_inline(b)}</li>" for b in bullets)
            parts.append(f'<ul class="prose-list">{items}</ul>')
            bullets.clear()

    for p in lines:
        if p.startswith("- "):
            bullets.append(p[2:].strip())
            continue
        flush()
        if p.startswith("### "):
            parts.append(f'<h3 class="prose-heading">{md_inline(p[4:].strip())}</h3>')
        elif re.fullmatch(r"-{3,}", p):
            parts.append('<hr class="prose-rule">')
        else:
            parts.append(f"<p>{md_inline(p)}</p>")
    flush()
    return "".join(parts)


def prose_html(r: Recipe) -> str:
    if not r.prose:
        return ""
    return '<div class="prose">' + prose_parts_html(r.prose) + "</div>"


def body_two_col(r: Recipe) -> str:
    # Fall back to prose so an image archetype never renders a blank body for a
    # recipe that has loose text but no ingredients/directions. Always append
    # notes so family stories/tips aren't dropped in image archetypes.
    if r.ingredients or r.directions:
        body = f'<div class="two-col">{ingredients_html(r)}{directions_html(r)}</div>'
    else:
        body = prose_html(r)
    return body + notes_html(r)


# --------------------------------------------------------------------------- archetypes


def render_half_page(r: Recipe) -> str:
    """A photo band across the text column, above the title, between the
    header and the recipe, or at the foot of the page. The band takes the
    height the text leaves (see BAND_MIN_IN), so a short recipe gets a big
    photograph and a long one a smaller one, and the page ends with its text."""
    zone = r.zone.lower()
    if "upper" in zone:
        return flex_photo_html(r, "photo--band photo--band-top") + header_html(r) + body_two_col(r)
    if "lower" in zone:
        return header_html(r) + body_two_col(r) + flex_photo_html(r, "photo--band photo--band-bottom")
    return header_html(r) + flex_photo_html(r, "photo--band photo--band-center") + body_two_col(r)


def render_hero(r: Recipe) -> str:
    return (
        flex_photo_html(r, "photo--hero")
        + '<div class="hero-panel"><div class="hero-body">'
        + f'<h1 class="title title--hero">{esc(r.title)}</h1>'
        + f'<p class="attr">{esc(r.attribution)}</p>'
        + meta_html(r)
        + body_two_col(r)
        + "</div></div>"
    )


def render_sidebar(r: Recipe) -> str:
    left = "left" in r.zone.lower()
    core = (ingredients_html(r) + directions_html(r)) if (r.ingredients or r.directions) else prose_html(r)
    text = f'<div class="sidebar-text">{core}{notes_html(r)}</div>'
    img = image_html(r, "img--sidebar")
    inner = (img + text) if left else (text + img)
    row_cls = "sidebar-row sidebar-row--left" if left else "sidebar-row"
    return header_html(r) + f'<div class="{row_cls}">' + inner + "</div>"


def render_inset_original(r: Recipe) -> str:
    pull = ""
    # lift a short punchy line from the directions if present
    for t in r.directions:
        if len(t) < 40 and t.endswith("!"):
            pull = t
            break
    pull_html = f'<p class="pull">{esc(pull)}</p>' if pull else ""
    inset = (
        f'<aside class="inset"><div class="inset-label">From the original</div>'
        f'<pre class="inset-text">{esc(r.original_text)}</pre></aside>'
        if r.original_text
        else ""
    )
    return (
        flex_photo_html(r, "photo--band photo--band-top")
        + header_html(r)
        + pull_html
        + '<div class="inset-row">'
        + f'<div class="inset-main">{ingredients_html(r)}{directions_html(r)}</div>'
        + inset
        + "</div>"
    )


# At or below this many ingredients there is no column to speak of, so the
# spread stacks the two blocks in a single measured column instead of leaving
# a narrow column all but empty beside the directions.
SPREAD_STACK_INGREDIENTS = 3


def render_spread_photo(r: Recipe) -> str:
    """Verso leaf of a Two-Page Spread: the photograph, full-bleed, nothing else.
    Emitted by expand_two_page(), never assigned to a recipe directly."""
    return image_html(r, "img--spread")


def render_spread_text(r: Recipe) -> str:
    """Recto leaf of a Two-Page Spread: the whole recipe at full size, with no
    photograph competing for the page — the facing leaf carries it.

    Two columns, as a recipe page is set: the ingredients in a narrow one
    (about 38% of the measure, subheads included) and the directions in the
    wide one, with the notes following the directions. Only when that single
    ingredient column cannot hold its list at full size does FIT_SCRIPT switch
    the page to `two-col--split` — a wider ingredient column in two sub-columns
    — and it decides by measuring the page, not by counting ingredients."""
    if not (r.ingredients or r.directions):
        return header_html(r) + prose_html(r) + notes_html(r)
    if r.ingredients and len(r.ingredients) <= SPREAD_STACK_INGREDIENTS and r.directions:
        # Too few ingredients to hold a column open beside the directions.
        body = f'<div class="spread-stack">{ingredients_html(r)}{directions_html(r)}</div>'
        return header_html(r) + body + notes_html(r)
    return (
        header_html(r)
        + f'<div class="two-col two-col--spread">{ingredients_html(r)}'
        + f'<div class="spread-main">{directions_html(r)}{notes_html(r)}</div></div>'
    )


def render_recipe_spread(r: Recipe) -> str:
    """Verso leaf of a Recipe Spread: a recipe longer than one full page of text,
    set as one composition across both facing pages.

    The spread is a four-column grid, two columns a page, hanging from the same
    top margin on both. The title block heads the verso; ingredients, then
    directions, then notes flow down the columns in reading order. Everything is
    emitted into the first column, and FIT_SCRIPT's flow step distributes it by
    measurement in the browser: it fills the verso's two columns, carries the
    rest to the recto (render_recipe_spread_recto), balances it there, and gives
    the photograph whatever height is left. No step, ingredient, or note is ever
    split, and an ingredient subhead or a section heading always travels with
    the item beneath it."""
    return (
        '<div class="rs rs--verso">'
        + header_html(r)
        + '<div class="rs-cols"><div class="rs-col">'
        + ingredients_html(r) + directions_html(r) + notes_html(r)
        + '</div><div class="rs-col"></div></div></div>'
    )


def render_recipe_spread_recto(r: Recipe) -> str:
    """Recto leaf of a Recipe Spread: a running head, two empty columns the flow
    step fills, and the photograph, which takes the rest of the page. Emitted by
    expand_two_page(), never assigned to a recipe directly."""
    photo = image_html(r, "rs-photo") if r.has_image else ""
    return (
        '<div class="rs rs--recto">'
        f'<p class="running-head">{esc(r.title)}, continued</p>'
        '<div class="rs-cols"><div class="rs-col"></div><div class="rs-col"></div></div>'
        f"{photo}</div>"
    )


def render_text_only(r: Recipe) -> str:
    """No photograph: a centered, framed typographic page. Handles both
    standard recipes (ingredients + directions) and prose items (neither)."""
    if r.ingredients and r.directions:
        body = body_two_col(r)  # already appends notes_html
    elif r.directions:
        body = (
            '<div class="single-col">' + directions_html(r) + notes_html(r) + "</div>"
        )
    else:
        # prose item (poems, tips): loose paragraphs + any notes
        paras = prose_parts_html(r.prose)
        note_paras = "".join(f"<p>{md_inline(n)}</p>" for n in r.notes)
        continues = " data-continues" if prose_continues(r) else ""
        body = f'<div class="prose"{continues}>{paras}{note_paras}</div>'
    return (
        '<div class="textonly">'
        + '<div class="to-head">'
        + f'<h1 class="title title--center">{esc(r.title)}</h1>'
        + (f'<p class="attr">{esc(r.attribution)}</p>' if r.attribution else "")
        + '<div class="rule rule--center"></div>'
        + meta_html(r)
        + "</div>"
        + body
        + "</div>"
    )


def render_prose_cont(r: Recipe) -> str:
    """The continuation leaf of a prose page too long for one (prose_continues()):
    the same frame under a running head. FIT_SCRIPT's flowProse() moves into it
    whatever the first page cannot hold. Emitted by expand_two_page(), never
    assigned directly."""
    return (
        '<div class="textonly">'
        f'<p class="running-head">{esc(r.title)}, continued</p>'
        '<div class="prose prose--cont"></div></div>'
    )


def render_title_page(r: Recipe) -> str:
    """The book's title page: title, accent rule, subtitle, and edition/year,
    centered both ways in the frame.

    Generated from book.title/subtitle/edition — there is no title-page/page.md,
    because every word on this page is already in the config and the cover
    renders from the same values. Two copies would be one too many.
    """
    sub = f'<p class="title-sub">{esc(r.attribution)}</p>' if r.attribution else ""
    year = f'<p class="title-year">{esc(r.prose[0])}</p>' if r.prose else ""
    return (
        '<div class="textonly textonly--title"><div class="title-block">'
        f'<h1 class="title title--center">{esc(r.title)}</h1>'
        '<div class="rule rule--center"></div>'
        f"{sub}{year}"
        "</div></div>"
    )


# --------------------------------------------------------------------------- reference pages
#
# The contents, contributors, and index are generated from the finished page
# order. Each is a list of groups — a heading and the rows beneath it — that
# paginate() packs into two columns per leaf, here in Python, so the leaf count
# is known before pages are numbered and the type never shrinks to fit.

# A row: (style, label, page number or None). The style is the row's li class.
Row = tuple[str, str, "int | None"]


class RefGroup(NamedTuple):
    head: Row
    chunks: list[list[Row]]   # each chunk stays in one column: a cook and their dishes
    repeat_head: bool = True  # restate the heading atop a column the group runs into


class RefStyle(NamedTuple):
    font: str        # file in assets/fonts/; the family follows from it
    weight: int
    size: float      # pt
    tracking: float  # letter-spacing, em
    upper: bool
    line: float      # line height, pt
    above: float     # space above the row, pt
    indent: float    # pt
    accent: bool     # set in the chapter accent rather than ink


# One source for both the CSS and the row heights paginate() budgets with, so
# the two cannot disagree. Heights are fixed per line, so a row's height is its
# line count times `line`, plus `above`.
REF_STYLES = {
    "ref-sec": RefStyle("PlayfairDisplay.ttf", 700, 10.5, 0.05, True, 14, 10, 0, True),
    "ref-name": RefStyle("PlayfairDisplay.ttf", 700, 11, 0, False, 14, 8, 0, True),
    "ref-letter": RefStyle("PlayfairDisplay.ttf", 700, 16, 0, False, 20, 10, 0, True),
    "ref-entry": RefStyle("SourceSans3.ttf", 400, 10, 0, False, 13.5, 0, 12, False),
    "ref-dish": RefStyle("SourceSans3.ttf", 400, 10, 0, False, 13.5, 0, 0, False),
    "ref-cook": RefStyle("SourceSans3.ttf", 600, 10, 0, False, 13.5, 3, 0, False),
}

# Inside a .textonly frame, in pt: the text block (MARGIN_IN, MARGIN_BOTTOM_IN
# from the trim) less the frame's 0.5in x 0.55in padding and 1.5pt borders. The
# same height in both builds; the screen draft's 8 in trim is the narrower width,
# so wrapping is budgeted on it and the print build, 36pt wider, only ever wraps
# less.
REF_FRAME_H = TEXT_AREA_IN * 72 - 2 * 0.5 * 72 - 3
REF_FRAME_W = (8.0 - 2 * MARGIN_IN) * 72 - 2 * 0.55 * 72 - 3
REF_HEAD_H = 64      # .ref-head: the page title and its rule
REF_GAP = 24         # between the two columns
REF_COL_W = (REF_FRAME_W - REF_GAP) / 2
REF_COL_H = REF_FRAME_H - REF_HEAD_H - 4  # 4pt slack for rounding in the browser
REF_PAGE_SLOT = 30   # leader dots' 6pt minimum + 8pt margins + a three-digit page number


@lru_cache(maxsize=None)
def _ref_font(file: str, weight: int):
    from PIL import ImageFont  # measuring is only needed for a full build
    font = ImageFont.truetype(str(FONT_DIR / file), 100)
    font.set_variation_by_axes([weight])
    return font


def _text_width(text: str, s: RefStyle) -> float:
    text = text.upper() if s.upper else text
    return (_ref_font(s.font, s.weight).getlength(text) / 100 + len(text) * s.tracking) * s.size


@lru_cache(maxsize=None)
def row_height(row: Row) -> float:
    """Rendered height of a row: greedy word wrap, as the browser does it, with
    2% spare per line so a measurement a hair short never costs a line."""
    style, label, page = row
    s = REF_STYLES[style]
    width = REF_COL_W - s.indent - (REF_PAGE_SLOT if page is not None else 0)
    lines, current = 1, ""
    for word in label.split():
        trial = f"{current} {word}" if current else word
        if current and _text_width(trial, s) * 1.02 > width:
            lines, current = lines + 1, word
        else:
            current = trial
    return s.above + lines * s.line


def paginate(groups: list[RefGroup]) -> list[list[list[Row]]]:
    """Pack groups into columns, two to a leaf: [leaf][column][row].

    A heading never ends a column — it moves to the next one with its first
    chunk. A group that runs over restates its heading, marked "(cont.)"."""
    cols: list[list[Row]] = [[]]
    used = 0.0

    def fits(rows: list[Row]) -> bool:
        return not cols[-1] or used + sum(map(row_height, rows)) <= REF_COL_H

    def place(rows: list[Row]) -> None:
        nonlocal used
        cols[-1].extend(rows)
        used += sum(map(row_height, rows))

    def next_column() -> None:
        nonlocal used
        cols.append([])
        used = 0.0

    for g in groups:
        if not fits([g.head, *(g.chunks[0] if g.chunks else [])]):
            next_column()
        place([g.head])
        for chunk in g.chunks:
            if not fits(chunk):
                next_column()
                if g.repeat_head:
                    place([(g.head[0], f"{g.head[1]} (cont.)", None)])
            place(chunk)
    return [cols[i:i + 2] for i in range(0, len(cols), 2)]


def is_entry_leaf(r: Recipe) -> bool:
    """The leaf an entry's title is on, which is where the contents, contributors,
    and index point: a Two-Page Spread's recipe leaf, a Recipe Spread's verso.
    Furniture and an entry's other leaves are never listed."""
    return not (r.is_divider or r.is_generated or r.is_blank or r.is_spread_photo
                or r.is_spread_cont or r.is_prose_cont or r.is_keepsake)


def toc_groups(shown: list[Recipe]) -> list[RefGroup]:
    """Each chapter in TOC_CATEGORIES, at its divider (or first page), with its
    entries beneath. A one-page or generated chapter is its own line."""
    divider_page = {r.slug: r.page_number for r in shown if r.is_divider}
    chapters: dict[str, list[Recipe]] = {}  # first appearance = page order
    for r in shown:
        if r.category in TOC_CATEGORIES and (is_entry_leaf(r) or r.is_generated):
            chapters.setdefault(r.category, []).append(r)
    groups = []
    for cat, items in chapters.items():
        label = CATEGORY_LABELS.get(cat, cat.replace("-", " ").title())
        head = ("ref-sec", label, divider_page.get(cat, items[0].page_number))
        if items[0].is_generated or (len(items) == 1 and items[0].is_chapter_page):
            groups.append(RefGroup(head, []))
        else:
            groups.append(RefGroup(head, [[("ref-entry", it.title, it.page_number)] for it in items]))
    return groups


_SUBMITTED_BY = re.compile(r"\s*\(submitted by [^)]*\)\s*$", re.IGNORECASE)


def credited_cooks(attribution: str) -> list[str]:
    """The people an attribution line credits, each named as written.

    "Ann Lee and Bob Lee" and "Ann Lee/Carol Lee" are two cooks each; in
    "Ruth and Tom Baker" the shared surname is
    lent to the first name. "(submitted by …)" credits the cook, not the person
    who passed the card along, so the submitter is not listed for it."""
    text = _SUBMITTED_BY.sub("", attribution).strip()
    names = [n.strip() for n in re.split(r"\s*/\s*|\s+and\s+|\s*&\s*", text) if n.strip()]
    if len(names) > 1:
        surname = names[-1].split()[-1]
        names = [n if " " in n else f"{n} {surname}" for n in names]
    return names


def _surname_key(name: str) -> tuple[str, str]:
    return name.split()[-1].casefold(), name.casefold()


def credited_dishes(shown: list[Recipe]) -> dict[str, list[Recipe]]:
    """Each credited cook -> the entries credited to them, in page order. Every
    attributed entry counts, recipes and prose alike; a one-page chapter (the
    dedication, the closing message) is the book's own voice, not an entry."""
    cooks: dict[str, list[Recipe]] = {}
    for r in shown:
        if is_entry_leaf(r) and not r.is_chapter_page:
            for name in credited_cooks(r.attribution):
                cooks.setdefault(name, []).append(r)
    return dict(sorted(cooks.items(), key=lambda kv: _surname_key(kv[0])))


def contributor_groups(shown: list[Recipe]) -> list[RefGroup]:
    """Every cook, by surname, named as written, with their dishes beneath."""
    return [
        RefGroup(("ref-name", name, None), [[("ref-entry", r.title, r.page_number)] for r in dishes])
        for name, dishes in credited_dishes(shown).items()
    ]


def _index_key(label: str) -> str:
    return re.sub(r"[^0-9a-z ]", "", label.casefold()).strip()


def index_groups(shown: list[Recipe]) -> list[RefGroup]:
    """A–Z of dish titles and cooks under letter headings. A cook files under
    the surname, inverted ("Baker, Ruth"), with their dishes beneath."""
    chunks: list[tuple[str, list[Row]]] = [
        (_index_key(r.title), [("ref-dish", r.title, r.page_number)])
        for r in shown if is_entry_leaf(r) and not r.is_chapter_page
    ]
    for name, dishes in credited_dishes(shown).items():
        *given, surname = name.split()
        inverted = f"{surname}, {' '.join(given)}" if given else surname
        chunks.append((_index_key(inverted), [("ref-cook", inverted, None)]
                       + [("ref-entry", r.title, r.page_number) for r in dishes]))
    chunks.sort(key=lambda c: (c[0], c[1][0][0]))
    letters: dict[str, list[list[Row]]] = {}
    for key, rows in chunks:
        letter = key[:1].upper() if key[:1].isalpha() else "#"
        letters.setdefault(letter, []).append(rows)
    return [RefGroup(("ref-letter", letter, None), rows, repeat_head=False)
            for letter, rows in letters.items()]


# Generated chapters whose pages are lists, by chapter name.
REFERENCE_GROUPS = {
    "table-of-contents": toc_groups,
    "contributors": contributor_groups,
    "index": index_groups,
}


def render_reference(r: Recipe) -> str:
    """One leaf of the contents, contributors, or index: the chapter label and
    the two columns paginate() gave this leaf. Every row's page number is the
    page it points at, filled in after the book's pages were numbered."""
    def row_html(row: Row) -> str:
        style, label, page = row
        leader = (f'<span class="ref-dots"></span><span class="ref-page">{page}</span>'
                  if page is not None else "")
        return f'<li class="{style}"><span class="ref-label">{esc(label)}</span>{leader}</li>'

    cols = "".join(f'<ul class="ref">{"".join(map(row_html, col))}</ul>' for col in r.columns)
    return (
        '<div class="textonly"><div class="ref-head">'
        f'<h1 class="title title--center">{esc(r.title)}</h1>'
        '<div class="rule rule--center"></div></div>'
        f'<div class="ref-cols">{cols}</div></div>'
    )


def reference_css() -> str:
    """The row styles, from REF_STYLES, so the CSS is the budget paginate() uses."""
    families = {"PlayfairDisplay.ttf": "'Playfair Display', Georgia, serif",
                "SourceSans3.ttf": "'Source Sans 3', sans-serif"}
    rules = [
        f".ref-head {{ height: {REF_HEAD_H}pt; flex: none; }}"
        f".ref-cols {{ flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr;"
        f" column-gap: {REF_GAP}pt; align-items: start; }}"
        "ul.ref { list-style: none; margin: 0; padding: 0; min-width: 0; }"
        "ul.ref li { display: flex; align-items: flex-end; margin: 0; }"
        ".ref-label { min-width: 0; }"
        ".ref-dots { flex: 1; min-width: 6pt; margin: 0 4pt 3pt; border-bottom: 1pt dotted var(--muted); }"
        ".ref-page { flex: none; font-family: 'Source Sans 3', sans-serif; font-size: 10pt;"
        " font-weight: 400; letter-spacing: 0; text-transform: none; color: var(--muted);"
        " font-variant-numeric: tabular-nums; }"
    ]
    for name, s in REF_STYLES.items():
        rules.append(
            f"ul.ref li.{name} {{ font-family: {families[s.font]}; font-weight: {s.weight};"
            f" font-size: {s.size}pt; letter-spacing: {s.tracking}em;"
            f" text-transform: {'uppercase' if s.upper else 'none'}; line-height: {s.line}pt;"
            f" padding: {s.above}pt 0 0 {s.indent}pt;"
            f" color: {'var(--accent)' if s.accent else 'var(--ink)'}; }}"
        )
    return "".join(rules)


# Generated chapters, by name: what renders each of their leaves.
GENERATED_RENDERERS = {
    "title-page": render_title_page,
    **{name: render_reference for name in REFERENCE_GROUPS},
}


def generated_page(chapter) -> Recipe:
    """The placeholder for a `kind: generated` chapter, at its place in the book.
    The reference pages expand into as many leaves as they need in build()."""
    page = Recipe(category=chapter.name, slug=chapter.name, archetype="Generated",
                  zone=chapter.name, title=chapter.label, origin="fixed", is_generated=True)
    if chapter.name == "title-page":
        page.title, page.attribution = CONFIG.title, CONFIG.subtitle
        page.prose = [CONFIG.edition] if CONFIG.edition else []
    return page


def expand_reference_pages(pages: list[Recipe], leaf_counts: dict[str, int]) -> list[Recipe]:
    """Each reference placeholder as its leaves: leaf_counts[name], else one."""
    out: list[Recipe] = []
    for r in pages:
        if r.is_generated and r.category in REFERENCE_GROUPS:
            n = leaf_counts.get(r.category, 1)
            out.extend(replace(r, zone=f"{r.category} {i}/{n}") for i in range(1, n + 1))
        else:
            out.append(r)
    return out


# --------------------------------------------------------------------------- extras
#
# An entry folder or a chapter folder may hold an extras/ folder of keepsakes —
# card scans, family photos, letters. Only the files listed in extras/extras.md
# print, in the order listed, one markdown image line each with the caption as
# alt text:  ![Ruth's original card, about 1975](ruth-card.jpg)
# Anything else in the line-up (a heading, a note to the family) is ignored, and
# an unlisted file just sits there safely — `cookbook lint` says it is not printed.

EXTRAS_DIR = "extras"
EXTRAS_LIST = "extras.md"
EXTRA_SUFFIXES = (".jpg", ".jpeg", ".png")
EXTRA_LINE = re.compile(r"^\s*!\[(?P<caption>[^\]]*)\]\((?P<file>[^)]+)\)\s*$")

# The inset is one row of at most this many items along the foot of the entry's
# own page; more than that is a keepsake page's worth.
INSET_MAX_ITEMS = 2
# A keepsake page holds at most this many rows (see keepsake_rows), so a card
# scan prints large enough to read; a longer list continues onto more pages.
KEEPSAKE_ROWS = 2

# Pages that can take an inset. Every other archetype — photo-led pages and the
# two-page layouts — has no slack to give, so its extras go on a keepsake page.
# On a framed text page the inset needs room below the text: INSET_ROOM is the
# most estimated body text (in lines; see _body_lines) that still leaves it free
# at full type size. On Half-Page Classic the band gives up the inset's height,
# so the inset fits when the band keeps its minimum after giving up INSET_IN.
# Calibrated by rendering every candidate page of a full-length book with an inset of one
# and of two items, in both the screen and the print geometry: framed text first
# zoomed at 10.9 lines; an inset took at most 2.9 in from a band (one landscape
# card on screen), and no band page with a predicted photo_room() of 5.9 in or
# more zoomed; dividers (larger inset) all fit.
# When in doubt the budget is lower: a keepsake page costs a leaf, while an
# inset that makes FIT_SCRIPT zoom shrinks recipe type toward the 10pt floor.
INSET_ROOM = {"Text-Only Framed": 10.8}
INSET_IN = 2.9
INSET_ARCHETYPES = ("Text-Only Framed", "Half-Page Classic")


def extras_listing(folder: Path) -> list[tuple[str, str]]:
    """(file name, caption) for each image line of folder/extras/extras.md, in
    order — the raw listing, whether or not the files exist."""
    listing = folder / EXTRAS_DIR / EXTRAS_LIST
    if not listing.exists():
        return []
    found = []
    for line in listing.read_text(encoding="utf-8").splitlines():
        m = EXTRA_LINE.match(line)
        if m:
            found.append((m.group("file").strip(), m.group("caption").strip()))
    return found


def load_extras(folder: Path) -> list[Extra]:
    """The printable extras of an entry or chapter folder: listed, present, and
    a supported image type. `cookbook lint` reports the rest."""
    base = folder / EXTRAS_DIR
    found = []
    for name, caption in extras_listing(folder):
        path = base / name
        if not (path.is_file() and path.suffix.lower() in EXTRA_SUFFIXES):
            continue
        from PIL import Image  # only a book with extras pays for the import
        with Image.open(path) as img:
            found.append(Extra(path=path, caption=caption, aspect=img.width / img.height))
    return found


def _lines(items: list[str], per_line: int) -> int:
    return sum(-(-len(s) // per_line) or 1 for s in items)


def _body_lines(r: Recipe) -> float:
    """Estimated rendered height of a page's body text, in lines of its type.

    The two-column recipe body is as tall as its taller column; prose flows in
    two balanced columns. Characters per line are each column's measure at the
    archetype's type size, which is all an estimate needs to be: the budgets in
    INSET_ROOM and FULL_TYPE_LINES carry the margin. In the recipe body an
    ingredient subhead costs its own line plus its top margin, each step adds
    the gap below it, a Notes block adds its heading, and a title too long for
    one line at the long-title size pushes the body down two lines — fitted
    against every recipe rendered in every archetype, this is what tells a page
    that fits at full type from one that does not."""
    message = [r.attribution] if (r.is_divider or r.is_chapter_page) and r.attribution else []
    if r.ingredients and r.directions:
        plain = [i for i in r.ingredients if not i.startswith("## ")]
        subheads = len(r.ingredients) - len(plain)
        ingredients = _lines(plain, 24) + 1.5 * subheads
        directions = _lines(r.directions, 56) + 0.3 * len(r.directions)
        notes = _lines(r.notes, 95) + 1 if r.notes else 0
        title = 2 if len(r.title) > 32 else 0
        return max(ingredients, directions) + notes + title
    if r.directions:
        return _lines(r.directions + r.notes, 75)
    return -(-_lines(message + r.prose + r.notes, 42) // 2)


def inset_has_room(r: Recipe, items: list[Extra]) -> bool:
    """Whether `items` can sit inset on r's own page without crowding its text.

    Deterministic, decided before anything is rendered; when in doubt, no —
    a keepsake page costs a leaf, an inset that triggers FIT_SCRIPT costs the
    cook their type size."""
    if len(items) > INSET_MAX_ITEMS or r.archetype not in INSET_ARCHETYPES:
        return False
    if r.extras_placement:
        return r.extras_placement == "inset"
    if r.archetype in PHOTO_RANGE:
        return photo_room(r, r.archetype) - INSET_IN >= PHOTO_RANGE[r.archetype][0]
    return _body_lines(r) <= INSET_ROOM[r.archetype]


def place_extras(pages: list[Recipe]) -> list[Recipe]:
    """Give each entry's and chapter's extras a place: inset on its own page when
    there is room (see inset_has_room), else keepsake leaves directly after it.

    A chapter's extras live in book/sections/{chapter}/extras/ and go with the
    chapter's divider or one-page chapter page. A keepsake leaf is a copy of its
    page — same chapter, accent, and title — flagged is_keepsake and stripped of
    the flags that would make pagination or the contents treat it as the page
    itself. It takes a folio but is never listed (TOC, index, contributors)."""
    out: list[Recipe] = []
    for r in pages:
        out.append(r)
        if r.is_generated or r.is_blank:
            continue
        items = load_extras(r.folder)
        if not items:
            continue
        if inset_has_room(r, items):
            r.extras = items
            continue
        rows = keepsake_rows(items)
        for i in range(0, len(rows), KEEPSAKE_ROWS):
            out.append(replace(
                r,
                category=r.slug if r.is_divider else r.category,
                archetype="Keepsake", zone="keepsake", origin="fixed",
                is_divider=False, is_chapter_page=False, is_keepsake=True,
                extras=[x for row in rows[i:i + KEEPSAKE_ROWS] for x in row],
            ))
    return out


def _extra_src(x: Extra) -> str:
    return f"{BOOK_REL}/{x.path.relative_to(BOOK).as_posix()}"


def extra_figure_html(x: Extra) -> str:
    cap = f"<figcaption>{md_inline(x.caption)}</figcaption>" if x.caption else ""
    return (
        f'<figure class="extra" style="--ar:{x.aspect:.4f}">'
        f'<img src="{esc(_extra_src(x))}" alt="{esc(x.caption)}">'
        f"{cap}</figure>"
    )


def extras_inset_html(r: Recipe) -> str:
    # A divider is a title and a line or two: its inset can be larger, and sits
    # centered in the open frame rather than at the foot.
    cls = "extras-inset extras-inset--opener" if r.is_divider else "extras-inset"
    figures = "".join(extra_figure_html(x) for x in r.extras)
    return f'<div class="{cls}">{figures}</div>'


def with_extras_inset(r: Recipe, inner: str) -> str:
    """Append r's inset to its rendered page. One helper for every archetype
    that can take one, rather than a branch in each renderer: a framed text page
    keeps the inset inside its frame, any other page sets it along the foot."""
    if not r.extras or r.is_keepsake:
        return inner
    inset = extras_inset_html(r)
    if inner.startswith('<div class="textonly') and inner.endswith("</div>"):
        return inner[: -len("</div>")] + inset + "</div>"
    return inner + inset


def keepsake_rows(items: list[Extra]) -> list[list[Extra]]:
    """Group a keepsake page's items into rows, in listed order: a landscape item
    — a recipe card, a group photo — takes the full width to itself, and
    consecutive portraits pair up side by side."""
    rows: list[list[Extra]] = []
    for x in items:
        if x.aspect < 1 and rows and len(rows[-1]) == 1 and rows[-1][0].aspect < 1:
            rows[-1].append(x)
        else:
            rows.append([x])
    return rows


def render_keepsake(r: Recipe) -> str:
    """A keepsake page: the entry's (or chapter's) extras, as large as the page
    allows, captioned in the italic serif, in the rows keepsake_rows() gives."""
    rows = keepsake_rows(r.extras)
    body = "".join(
        '<div class="keepsake-row">' + "".join(extra_figure_html(x) for x in row) + "</div>"
        for row in rows
    )
    return (
        '<div class="keepsake">'
        '<div class="keepsake-head"><p class="keepsake-kicker">Keepsakes</p>'
        f'<h1 class="keepsake-title">{esc(r.title)}</h1></div>'
        f'<div class="keepsake-grid" style="--rows:{len(rows)}">{body}</div>'
        "</div>"
    )


RENDERERS = {
    "Two-Page Spread": render_spread_text,
    "Recipe Spread": render_recipe_spread,
    "Half-Page Classic": render_half_page,
    "Hero Full-Bleed": render_hero,
    "Sidebar Portrait": render_sidebar,
    "Inset Original": render_inset_original,
    "Text-Only Framed": render_text_only,
}


def render_page(r: Recipe) -> str:
    # A blank leaf inserted for recto pagination: bare paper page, no folio/tag.
    if r.is_blank:
        verso = "page--verso" if r.page_number and r.page_number % 2 == 0 else ""
        return f'<section class="page {verso}" style="--accent:{r.accent}"></section>'
    if r.is_generated:
        renderer = GENERATED_RENDERERS[r.category]
    elif r.is_spread_photo:
        renderer = render_spread_photo
    elif r.is_spread_cont:
        renderer = render_recipe_spread_recto
    elif r.is_prose_cont:
        renderer = render_prose_cont
    elif r.is_keepsake:
        renderer = render_keepsake
    else:
        renderer = RENDERERS.get(r.archetype, render_text_only)
    inner = with_extras_inset(r, renderer(r))
    pad = "page--nopad" if (r.archetype == "Hero Full-Bleed" or r.is_spread_photo) else ""
    # Mirror the binding gutter: even (verso) pages get it on the right. The
    # screen draft mirrors it too, since it lays the pages out as spreads.
    verso = "page--verso" if r.page_number and r.page_number % 2 == 0 else ""
    label = " &middot; ".join(esc(part) for part in (r.archetype, r.zone, r.origin) if part)
    # A full-bleed photo leaf takes no folio — there is no paper to print it on.
    show_folio = r.page_number and not r.is_spread_photo
    page_num = f'<div class="page-number">{r.page_number}</div>' if show_folio else ""
    return (
        f'<section class="page {pad} {verso}" id="p{r.page_number}" style="--accent:{r.accent}">'
        f'<div class="page-inner">{inner}</div>'
        f"{page_num}"
        f'<div class="page-tag">{label}</div>'
        f"</section>"
    )


# --------------------------------------------------------------------------- css / document

CSS = """
:root { --paper:#faf7f1; --ink:#2c2723; --muted:#6b6259; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background:#d9d4cc; }
body { font-family: 'Source Sans 3', 'Helvetica Neue', Arial, sans-serif; color: var(--ink);
  font-weight: 400; }
/* On screen the pages sit as the reader meets them, in facing pairs: page 1
   alone on the right, then 2|3, 4|5, ... — so a two-page recipe is reviewed as
   the spread it is. Printing keeps one page per sheet. */
.book { display: grid; grid-template-columns: repeat(2, var(--page-w)); justify-content: center;
  row-gap: 0.35in; padding: 0.35in; }
.book > .page:first-child { grid-column: 2; }

.page {
  position: relative; width: var(--page-w); height: var(--page-h); background: var(--paper);
  padding: var(--pad-t) var(--pad-outer) var(--pad-b) var(--pad-inner); overflow: hidden;
    box-shadow: 0 2px 14px rgba(0,0,0,.22); page-break-after: always;
    print-color-adjust: exact; -webkit-print-color-adjust: exact;
}
/* Recto (odd, right-hand) pages keep the gutter on the left via the base
   padding above; verso (even, left-hand) pages mirror it. */
.page--verso { padding-left: var(--pad-outer); padding-right: var(--pad-inner); }
.page--nopad { padding: 0; }
.page-inner { position: relative; width: 100%; height: 100%; display: flex; flex-direction: column; }
.page-tag {
  position: absolute; bottom: 0.14in; right: 0.2in; font-size: 6.5pt; letter-spacing: .04em;
  text-transform: uppercase; color: var(--muted); opacity: .65;
}
.page-number {
    position: absolute; bottom: var(--pnum-bottom); left: 50%; transform: translateX(-50%);
    font-size: 8pt; color: var(--muted);
}
/* Framed text-only pages: the frame's bottom border lands at --pad-b, right on
   top of the default folio position — tuck the number inside the frame's empty
   bottom padding instead of letting it sit on the line. */
.page:has(.textonly) .page-number { bottom: calc(var(--pad-b) + 0.09in); }
@media print { .page-tag { display: none; } .book { display: block; padding: 0; } .page { box-shadow: none; } }

/* Typography */
.title { font-family: 'Playfair Display', Georgia, serif; font-weight: 700; font-size: 40pt;
  line-height: 1.03; margin: 0; color: var(--ink); }
.title--long { font-size: 28pt; }
.attr { font-family: 'Playfair Display', Georgia, serif; font-style: italic; font-weight: 500;
  font-size: 15pt; color: var(--muted); margin: 4pt 0 0; }
.rule { height: 2px; background: var(--accent); width: 100%; margin: 9pt 0; }
.rule--center { width: 44pt; margin: 9pt auto; height: 2.5px; }
.meta { display: flex; flex-wrap: wrap; gap: 4pt 20pt; }
.meta-item { display: flex; flex-direction: column; gap: 1pt; }
.meta-label { font-family: 'Source Sans 3', sans-serif; font-size: 7pt; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase; color: var(--accent); }
.meta-val { font-size: 9.5pt; color: var(--ink); }
.sec { font-family: 'Source Sans 3', sans-serif; font-weight: 600; font-size: 11pt;
  letter-spacing: .14em; text-transform: uppercase; color: var(--accent); margin: 0 0 5pt; }
.header { margin-bottom: 10pt; }

.two-col { display: grid; grid-template-columns: 1fr 1.7fr; gap: 16pt; margin-top: 12pt; flex: 1; }
.block { min-width: 0; }
ul.ingredients { list-style: none; margin: 0; padding: 0; }
ul.ingredients li { font-size: 10.5pt; line-height: 1.35; padding: 1.5pt 0 1.5pt 12pt;
  position: relative; }
ul.ingredients li:not(.subhead):before { content: "•"; color: var(--accent); position: absolute; left: 0; }
ul.ingredients li.subhead { font-weight: 700; color: var(--accent); text-transform: uppercase;
  font-size: 9pt; letter-spacing: .08em; padding-left: 0; margin-top: 7pt; }
ol.directions { margin: 0; padding-left: 16pt; }
ol.directions li { font-size: 10.5pt; line-height: 1.4; margin-bottom: 4pt; padding-left: 3pt; }

/* Images */
.img { display: block; object-fit: cover; object-position: center; border-radius: 3pt; }
.img--placeholder { display: flex; align-items: center; justify-content: center; color: var(--muted);
  background: #efe9df; border: 1px dashed #c9bfb0; font-size: 10pt; font-style: italic; }
/* A photo band takes the height the text leaves it, between --band-min and
   --band-max (BAND_MIN_IN, BAND_MAX_IN). It is the page's only growing child —
   the recipe body keeps its own height — so a page ends with its text, not
   with paper. FIT_SCRIPT frames the image in the box once its size is known
   (framePhotos); until then it is a centered cover. The margins keep the photo
   off the type: the band, not the text, gives up that room. */
.photo { position: relative; overflow: hidden; border-radius: 3pt; }
.photo > img { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: cover; }
.photo--band { flex: 1 1 0; min-height: var(--band-min); max-height: var(--band-max); }
.page-inner:has(> .photo--band) > .two-col, .page-inner:has(> .photo--band) > .inset-row { flex: none; }
.photo--band-top { margin-bottom: 14pt; }
.photo--band-center { margin: 10pt 0; }
.photo--band-bottom { margin-top: 14pt; }
/* Two-Page Spread, verso leaf: the photograph is the whole page. Absolute so it
   ignores .page padding entirely and runs into the bleed on all four edges. */
.img--spread { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 0; }
/* Recto leaf: a whole page for one recipe, set in two columns — ingredients in
   the narrow one (about 38% of the measure), directions and then notes in the
   wide one. The body does not stretch, so any spare paper stays at the foot.
   `two-col--split` is FIT_SCRIPT's fallback for a list the narrow column cannot
   hold at full size: a wider ingredient column, flowed in two sub-columns. */
.two-col--spread { grid-template-columns: 38fr 62fr; gap: 22pt; flex: none; }
.spread-main { min-width: 0; }
.two-col--split { grid-template-columns: 1.15fr 1fr; }
.two-col--split ul.ingredients { column-count: 2; column-gap: 16pt; }
.two-col--split ul.ingredients li { break-inside: avoid; -webkit-column-break-inside: avoid; }
.two-col--split ul.ingredients li.subhead { break-after: avoid; -webkit-column-break-after: avoid; }
/* A recipe whose ingredients are a line or two: stack the blocks in one column
   at a readable measure rather than holding an empty column open beside them. */
.spread-stack { max-width: 5.4in; margin: 0 auto; }
.spread-stack .block + .block { margin-top: 16pt; }
/* Recipe Spread: one recipe too long for a page, composed across both facing
   pages on a four-column grid, two columns a page, from the same top margin.
   FIT_SCRIPT's flow step fills the columns by measurement; the recto's
   photograph is the flex child that takes the height left under its columns,
   or a band under the verso's title block when that height is too little. A
   recto the verso left no text for drops its running head and columns. */
.rs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.rs-cols { display: grid; grid-template-columns: 1fr 1fr; column-gap: 22pt; align-items: start; }
.rs--verso .rs-cols { flex: 1; min-height: 0; grid-template-rows: minmax(0, 1fr);
  align-items: stretch; margin-top: 12pt; }
.rs-col { min-width: 0; min-height: 0; }
.rs-col .block + .block { margin-top: 14pt; }
.rs-col > .block:first-child > ul > li.subhead:first-child { margin-top: 0; }
.running-head { font-size: 8pt; font-weight: 700; letter-spacing: .16em; text-transform: uppercase;
  color: var(--accent); margin: 0 0 14pt; padding-bottom: 6pt;
  border-bottom: 1pt solid color-mix(in srgb, var(--accent) 45%, var(--paper)); }
.rs--recto:not(:has(li)) > .running-head, .rs--recto:not(:has(li)) > .rs-cols { display: none; }
.rs-photo { flex: 1 1 0; min-height: 0; width: 100%; margin-top: 18pt; }
.rs--recto:not(:has(li)) > .rs-photo { margin-top: 0; }
.rs-photo--band { flex: none; height: 2.5in; margin: 2pt 0 2pt; }
/* Hero: the photograph runs full-bleed from the top of the page box down to
   the opaque paper panel, which is as tall as its text. The photo is the
   page's growing child, between --hero-min and --hero-max (HERO_MIN_IN,
   HERO_MAX_IN), so a short recipe gets a taller picture rather than a panel of
   empty paper; past the maximum the panel takes the rest. No alpha gradient —
   a soft fade needs transparency, which print preflights flag — a thin accent
   rule marks the clean photo/panel seam. */
.photo--hero { flex: 1 1 0; min-height: var(--hero-min); max-height: var(--hero-max); border-radius: 0; }
.hero-panel { flex: none; background: var(--paper); border-top: 2.5px solid var(--accent);
  padding: 0.5in var(--pad-inner) var(--pad-b) var(--pad-inner); display: flex; flex-direction: column; }
.hero-body { display: flex; flex-direction: column; }
.hero-panel .title--hero { font-size: 34pt; }
.hero-panel .attr { margin-bottom: 8pt; }

/* The row is exactly the space left under the header. Left as an auto track,
   the portrait photo's intrinsic height at column width (~8.8in) sized the row
   past the page bottom, and FIT_SCRIPT zoomed every sidebar page to 0.941 no
   matter how little text it held. */
.sidebar-row { display: grid; grid-template-columns: 1fr 0.85fr; grid-template-rows: minmax(0, 1fr);
  gap: 18pt; flex: 1; min-height: 0; }
.sidebar-row--left { grid-template-columns: 0.85fr 1fr; }
.sidebar-text { display: flex; flex-direction: column; }
.sidebar-text .block { margin-bottom: 10pt; }
.img--sidebar { width: 100%; height: 100%; }

.pull { font-family: 'Playfair Display', Georgia, serif; font-style: italic; font-weight: 500;
  font-size: 19pt; color: var(--accent); margin: 12pt 0 4pt; text-align: center; }
.inset-row { display: grid; grid-template-columns: 1fr 0.8fr; gap: 16pt; margin-top: 8pt; flex: 1; }
.inset-main { display: flex; flex-direction: column; }
.inset { background: color-mix(in srgb, var(--accent) 9%, var(--paper)); border: 1px solid
  color-mix(in srgb, var(--accent) 30%, var(--paper)); border-radius: 4pt; padding: 12pt; align-self: start; }
.inset-label { font-size: 8pt; letter-spacing: .1em; text-transform: uppercase; color: var(--accent);
  margin-bottom: 6pt; }
.inset-text { font-family: 'Source Sans 3', sans-serif; font-size: 9pt; line-height: 1.4;
  white-space: pre-wrap; margin: 0; color: var(--ink); }

/* Text-Only Framed */
.textonly { flex: 1; display: flex; flex-direction: column; border: 1.5pt solid
  color-mix(in srgb, var(--accent) 45%, var(--paper)); border-radius: 4pt; padding: 0.5in 0.55in; }
.to-head { text-align: center; margin-bottom: 16pt; }
.textonly--title { justify-content: center; align-items: center; text-align: center; }
.title-block { max-width: 5.5in; }
.title-sub { font-family: 'Playfair Display', Georgia, serif; font-style: italic;
  font-weight: 500; font-size: 21pt; color: var(--muted); margin-top: 12pt; }
.title-year { font-size: 12pt; letter-spacing: .22em; text-transform: uppercase;
  color: var(--accent); font-weight: 700; margin-top: 18pt; }
.title--center { text-align: center; }
.to-head .attr { margin-top: 5pt; }
.to-head .meta { justify-content: center; }
.prose { column-count: 2; column-gap: 22pt; }
.prose p { font-size: 11pt; line-height: 1.55; margin: 0 0 9pt; break-inside: avoid; }
.prose-list { margin: 0 0 9pt; padding-left: 16pt; break-inside: avoid; }
.prose-list li { font-size: 11pt; line-height: 1.55; }
.prose-heading { column-span: all; font-family: 'Source Sans 3', sans-serif; font-weight: 600;
  font-size: 10pt; letter-spacing: .14em; text-transform: uppercase; color: var(--accent);
  text-align: center; margin: 4pt 0 10pt; }
.prose-rule { column-span: all; border: none; border-top: 1.5pt solid
  color-mix(in srgb, var(--accent) 45%, var(--paper)); margin: 6pt 0 14pt; }
.single-col { max-width: 5in; margin: 0 auto; }
.block--notes { margin-top: 10pt; }
ul.notes { margin: 0; padding-left: 14pt; }
ul.notes li { font-size: 10pt; line-height: 1.4; margin-bottom: 3pt; color: var(--muted); }

/* Extras: keepsakes listed in an entry's or chapter's extras/extras.md. Each
   figure carries its image's aspect ratio (--ar) so the picture is sized
   exactly — no letterbox — and its caption sits right beneath it. No shadow:
   a soft shadow is transparency, which print preflight flags. */
.extra { margin: 0; display: flex; flex-direction: column; align-items: center; min-width: 0; }
.extra img { display: block; aspect-ratio: var(--ar); height: auto;
  border: 0.75pt solid color-mix(in srgb, var(--ink) 20%, var(--paper)); }
.extra figcaption { font-family: 'Playfair Display', Georgia, serif; font-style: italic;
  font-weight: 500; font-size: 10.5pt; line-height: 1.3; color: var(--muted);
  text-align: center; margin-top: 5pt; }
/* Inset: one row along the foot of the entry's own page, below its text. */
.extras-inset { margin-top: auto; padding-top: 16pt; display: flex; justify-content: center;
  gap: 20pt; }
.extras-inset .extra { flex: 0 1 calc(2.3in * var(--ar)); }
.extras-inset .extra img { width: 100%; }
/* On a divider the inset is larger and centered in the open frame. */
.extras-inset--opener { margin: auto 0; padding-top: 0; }
.extras-inset--opener .extra { flex-basis: calc(4in * var(--ar)); }
/* A photo band gives up height to make the inset's room. Outside a frame
   the inset sits on the bottom margin; where the folio rises above that margin
   (the print geometry), the inset stops short of it. */
.page-inner > .extras-inset, .keepsake-grid {
  padding-bottom: max(0in, calc(var(--pnum-bottom) + 0.2in - var(--pad-b))); }
/* Keepsake page: the items as large as the page allows. Each grid cell is a
   size container, so an image takes the cell's width or its height less a
   caption allowance — whichever binds first. */
.keepsake { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.keepsake-head { text-align: center; margin-bottom: 18pt; }
.keepsake-kicker { font-size: 8pt; font-weight: 700; letter-spacing: .16em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 4pt; }
.keepsake-title { font-family: 'Playfair Display', Georgia, serif; font-style: italic;
  font-weight: 500; font-size: 20pt; line-height: 1.15; color: var(--ink); margin: 0; }
.keepsake-grid { flex: 1; min-height: 0; display: grid;
  grid-template-rows: repeat(var(--rows), minmax(0, 1fr)); gap: 24pt; }
.keepsake-row { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr);
  gap: 20pt; min-height: 0; }
.keepsake .extra { container-type: size; justify-content: center; min-height: 0; }
.keepsake .extra img { width: min(100cqw, (100cqh - 0.55in) * var(--ar)); }

/* Contents, contributors, index: row styles follow from REF_STYLES */
""" + reference_css()


# The book's section structure: which categories exist and in what order they're
# bound, with front matter first and back matter last.
BOOK_STRUCTURE = CONFIG.book_structure

# Categories that get a section-divider page inserted before their first entry,
# with the message from book/sections/{chapter}/page.md when it exists. Chapters
# with `divider: false` (front/back matter) don't get one.
DIVIDER_CATEGORIES = CONFIG.divider_categories

# Explicit slug order overrides for categories where alphabetical sorting reads
# wrong — front matter must open with the title page, then the dedication.
# Anything in a category's folder but not listed here falls back to alphabetical,
# appended after the listed slugs.
PINNED_ENTRIES: dict[str, list[str]] = CONFIG.pinned_entries


def ordered_slugdirs(catdir: Path, pinned: list[str]) -> list[Path]:
    """Pinned entries first, in the order listed; the rest alphabetically after."""
    remaining = {p.name: p for p in catdir.iterdir() if p.is_dir()}
    ordered = [remaining.pop(name) for name in pinned if name in remaining]
    ordered += sorted(remaining.values(), key=lambda p: p.name)
    return ordered


def enumerate_recipes() -> list[Recipe]:
    """Every recipe/page folder in book order. Manifest rows win (curated); the
    rest are stubs to be auto-assigned an archetype after parsing.

    Each name resolves to one of two bases via base_for(): recipe chapters under
    book/recipes/{name}/{slug}/recipe.md, and everything prose — including front
    and back matter — under book/sections/{name}/{slug}/page.md, so book/recipes/
    only ever holds actual recipes. A divider is inserted ahead of each
    DIVIDER_CATEGORIES chapter's first entry automatically; its message, if any,
    comes from book/sections/{chapter}/page.md. A `kind: generated` chapter —
    title page, contents, contributors, index — is a placeholder at its place in
    the list, with no folder behind it; build() fills it in."""
    manifest = {(m.category, m.slug): m for m in parse_manifest()}

    # A category folder that isn't in book.yaml's chapters still renders — at the
    # end, rather than vanishing — so a newly added chapter is visible before it
    # has been given a position. Both bases are searched, or a new prose chapter
    # would disappear instead of rendering late.
    seen_categories = list(BOOK_STRUCTURE)
    for base_name in ("recipes", "sections"):
        base = BOOK / base_name
        if not base.is_dir():
            continue
        for extra in sorted(p.name for p in base.iterdir() if p.is_dir()):
            if extra not in seen_categories:
                seen_categories.append(extra)

    recipes: list[Recipe] = []
    for cat in seen_categories:
        chapter = CONFIG.by_name.get(cat)
        if chapter and chapter.generated:
            recipes.append(generated_page(chapter))
            continue
        base_name = base_for(cat)
        catdir = BOOK / base_name / cat
        if not catdir.is_dir():
            continue

        # A chapter opens with a divider because book.yaml says so, not because
        # a file happens to exist. The page.md holds only the message, and a
        # divider carrying just its chapter name is a fine section opener.
        if cat in DIVIDER_CATEGORIES:
            recipes.append(Recipe(category="section-dividers", slug=cat, archetype="", zone="",
                                  base=base_name, is_divider=True))

        md_filename = "recipe.md" if base_name == "recipes" else "page.md"

        # A chapter with `divider: false` and a page of its own is a one-page
        # chapter — a dedication, a closing message — rendered in the flow rather
        # than forced onto a recto like a section opener.
        if cat not in DIVIDER_CATEGORIES and (BOOK / "sections" / cat / "page.md").exists():
            recipes.append(Recipe(category=cat, slug=cat, archetype="", zone="",
                                  base=base_name, is_chapter_page=True))
            continue

        for slugdir in ordered_slugdirs(catdir, PINNED_ENTRIES.get(cat, [])):
            slug = slugdir.name
            if not (slugdir / md_filename).exists():
                continue
            row = manifest.get((cat, slug))
            if row:
                row.origin = "curated"
                row.base = base_name
                recipes.append(row)
            else:
                recipes.append(Recipe(category=cat, slug=slug, archetype="", zone="", base=base_name))
    return recipes


# Rotations give each section deliberate variety instead of one repeated look.
IMG_ROTATION = [
    ("Half-Page Classic", "upper-half"),
    ("Sidebar Portrait", "sidebar-right"),
    ("Half-Page Classic", "lower-half"),
    ("Hero Full-Bleed", "full-bleed"),
    ("Half-Page Classic", "centered-half"),
    ("Sidebar Portrait", "sidebar-left"),
]
TEXT_ROTATION = [
    ("Text-Only Framed", "no image"),
]


# How tall a band page's text runs in the press build, in inches, measured on
# every photo recipe in the book set as a band page: each block's height is a
# per-line height times its lines at the block's measure (characters per line),
# plus a per-item allowance. Fitted to within 0.24 in of the measured room for
# every recipe — under the 0.33 in FIT_SCRIPT may take back by zooming a page to
# its 10pt floor, so a recipe band_room() admits never prints under 10pt.
# Re-measure when the band page's type, margins, or page geometry change.
BAND_TEXT_AREA_IN = TEXT_AREA_IN
BAND_GAPS_IN = 0.649       # header, recipe-body, and photo margins (the centered band's, the widest)
BAND_SECTION_HEAD_IN = 0.316  # an Ingredients or Directions heading
BAND_TITLE_IN = {24: 1.527, 38: 1.355}  # the header by title length; 28pt titles from 25 characters
BAND_TITLE_TWO_LINES_IN = 1.756
BAND_INGREDIENT_LINE_IN, BAND_INGREDIENT_MEASURE, BAND_SUBHEAD_IN = 0.231, 38, 0.274
BAND_STEP_LINE_IN, BAND_STEP_MEASURE, BAND_STEP_GAP_IN = 0.208, 63, 0.042
BAND_NOTES_HEAD_IN, BAND_NOTE_LINE_IN, BAND_NOTE_MEASURE, BAND_NOTE_GAP_IN = 0.458, 0.091, 60, 0.088


def _band_title(r: Recipe) -> float:
    """The band page's header height for r's title, in inches."""
    return next((h for limit, h in BAND_TITLE_IN.items() if len(r.title) <= limit),
                BAND_TITLE_TWO_LINES_IN)


def band_room(r: Recipe) -> float:
    """The height, in inches, r's text leaves a band's photo at full type in the
    press build (see BAND_TEXT_AREA_IN): negative when the text alone overruns
    the page."""
    if r.ingredients or r.directions:
        plain = [i for i in r.ingredients if not i.startswith("## ")]
        ingredients = (BAND_INGREDIENT_LINE_IN * _lines(plain, BAND_INGREDIENT_MEASURE)
                       + BAND_SUBHEAD_IN * (len(r.ingredients) - len(plain)))
        steps = (BAND_STEP_LINE_IN * _lines(r.directions, BAND_STEP_MEASURE)
                 + BAND_STEP_GAP_IN * len(r.directions))
        body = BAND_SECTION_HEAD_IN + max(ingredients, steps)
    else:
        body = BAND_STEP_LINE_IN * _body_lines(r)
    notes = (BAND_NOTES_HEAD_IN + BAND_NOTE_LINE_IN * _lines(r.notes, BAND_NOTE_MEASURE)
             + BAND_NOTE_GAP_IN * len(r.notes)) if r.notes else 0.0
    return BAND_TEXT_AREA_IN - _band_title(r) - BAND_GAPS_IN - body - notes


# The hero page's panel, besides its recipe body (as band_room() measures it):
# the 0.5 in top padding, the bottom padding (bleed + MARGIN_BOTTOM_IN), the
# accent rule, and the header with its 34pt title on one line. The title is
# 34pt at every length, so one longer than HERO_TITLE_ONE_LINE characters
# takes a second line, HERO_TITLE_WRAP_IN more. Fitted on every photo recipe in
# the book set as a hero page in the press build: within 0.24 in of the
# measured photo room, except a title just past the limit whose letters happen
# to fit one line, where it errs low (a smaller predicted photo).
HERO_PANEL_IN = 3.05
HERO_TITLE_ONE_LINE = 29
HERO_TITLE_WRAP_IN = 0.47
HERO_ROOM_SPARE_IN = 0.24


# The photo range of each flexible frame (see PHOTO_FRAMES), in inches.
PHOTO_RANGE = {
    "Hero Full-Bleed": (HERO_MIN_IN, HERO_MAX_IN),
    "Half-Page Classic": (BAND_MIN_IN, BAND_MAX_IN),
    "Inset Original": (BAND_MIN_IN, BAND_MAX_IN),
}


def photo_room(r: Recipe, archetype: str) -> float:
    """The height, in inches, r's text leaves a flexible frame's photo at full
    type in the press build (band_room()). The hero's photo is the page box
    less its text panel."""
    if archetype == "Hero Full-Bleed":
        body = BAND_TEXT_AREA_IN - BAND_GAPS_IN - _band_title(r) - band_room(r)
        wrap = HERO_TITLE_WRAP_IN if len(r.title) > HERO_TITLE_ONE_LINE else 0.0
        return PRINT_PAGE_H_IN - HERO_PANEL_IN - wrap - body
    return band_room(r)


def photo_height(r: Recipe, archetype: str) -> float:
    """The photo height a flexible frame gives r in the press build: its
    photo_room() held to the frame's PHOTO_RANGE."""
    low, high = PHOTO_RANGE[archetype]
    return min(high, max(low, photo_room(r, archetype)))


# The most estimated body text (_body_lines) each fixed-frame archetype holds
# at full type size, so FIT_SCRIPT never has to shrink a recipe below the 10pt
# floor that `cookbook check` enforces. Calibrated in the press build by
# rendering every recipe in every archetype and measuring the zoom FIT_SCRIPT
# would need: each budget sits just under the lowest estimate of any page that
# would print under 10pt. The estimate is coarse, so a budget can exclude a
# recipe that would have fit (it moves on to a roomier layout) but never admits
# one that the calibration saw fail; `cookbook check` remains the gate.
#
# A recipe over budget in every one-page layout open to it takes two pages. The
# "Two-Page Spread" budget is its recipe leaf: the whole recipe on one full
# text page facing a full-page photograph, calibrated the same way, with the
# sample widened by variants of the longest recipes (steps or ingredients
# repeated); the lowest estimate to print under 10pt was 38.6. A recipe longer
# than that, or one with no photograph to face it, gets the Recipe Spread, which
# flows the text across both pages.
# Recalibrate when page geometry or an archetype's type changes. The band and
# the hero have no budget: they hold a recipe whose text leaves their photo
# its minimum height (photo_room()).
FULL_TYPE_LINES = {
    "Sidebar Portrait": 19.4,
    "Text-Only Framed": 27.7,
    "Two-Page Spread": 38.5,
}
# The sidebar's text column is as tall as its photograph, so a recipe shorter
# than half the column leaves the column mostly empty paper beside the
# picture; it takes a band or the hero.
SIDEBAR_MIN_LINES = FULL_TYPE_LINES["Sidebar Portrait"] / 2
# The most estimated prose (_body_lines) a framed prose page holds at its full
# 11pt. Calibrated like FULL_TYPE_LINES, on the book's prose entries and longer
# and shorter variants of them, in both builds: 22 lines fit, 24 first zoomed.
# A longer prose page continues on the next leaf (prose_continues()).
PROSE_PAGE_LINES = 23
TWO_PAGE_SPREAD = ("Two-Page Spread", "photo verso + recipe recto")
RECIPE_SPREAD = ("Recipe Spread", "flowed across the spread")


def _rotate(rotation: list[tuple[str, str]], i: int, fits: Callable[[str], bool],
            prev: tuple[str, str]) -> tuple[tuple[str, str] | None, int]:
    """The next layout in `rotation` from position i whose archetype `fits` the
    recipe, preferring one that doesn't repeat the previous page's exact look;
    and the rotation position after it. (None, i) when none fits."""
    n = len(rotation)
    fitting = [k for k in range(i, i + n) if fits(rotation[k % n][0])]
    k = next((k for k in fitting if rotation[k % n] != prev), fitting[0] if fitting else None)
    return (None, i) if k is None else (rotation[k % n], k + 1)


def prose_continues(r: Recipe) -> bool:
    """Whether r is a framed prose page — an entry or a chapter's own page, not
    a divider — too long for one leaf at full size, so it continues on the next
    (see render_prose_cont())."""
    return (r.archetype == "Text-Only Framed" and bool(r.prose) and not r.is_divider
            and not (r.ingredients or r.directions) and not r.is_prose_cont
            and not r.is_keepsake and _body_lines(r) > PROSE_PAGE_LINES)


def holds_at_full_type(r: Recipe, archetype: str) -> bool:
    """Whether r's text suits `archetype` at full type: for a flexible frame,
    it leaves the photo at least its minimum height (photo_room()) — the hero
    with HERO_ROOM_SPARE_IN on top, the model's error, since a recipe it turns
    away still has the band, at no cost of a page; otherwise it is within the
    FULL_TYPE_LINES budget — and for the sidebar, at least SIDEBAR_MIN_LINES."""
    if archetype in PHOTO_RANGE:
        spare = HERO_ROOM_SPARE_IN if archetype == "Hero Full-Bleed" else 0.0
        return photo_room(r, archetype) - spare >= PHOTO_RANGE[archetype][0]
    lines = _body_lines(r) if (r.ingredients or r.directions) else 0
    if archetype == "Sidebar Portrait" and lines < SIDEBAR_MIN_LINES:
        return False
    return lines <= FULL_TYPE_LINES[archetype]


def assign_section(section: list[Recipe], prev: tuple[str, str]) -> tuple[str, str]:
    """Assign archetypes across one section (category) with variety: rotate
    image and text layouts, and never repeat the previous page's exact look.
    `prev` carries across section boundaries so text pages don't collide there.

    A layout is only chosen if the recipe fits it at full type
    (holds_at_full_type()) and its photo frame shows the dish (photo_fit()).
    A standing subject the sidebar's column suits — a glass, a mug — takes the
    column first. When the recipe fits one-page layouts but its photo suits
    none of their frames, it takes the band or hero that shows the most of the
    food — the sidebar only when no band or hero holds the text — and
    `cookbook fit` reports the photo as a candidate for regeneration: a photo
    never costs a second page. Only a recipe whose text fits nothing on one
    page takes two (see FULL_TYPE_LINES): the Two-Page Spread when its recipe
    leaf holds the text and its photo suits a full page, else the Recipe
    Spread, whose photo takes the room the flowed text leaves."""
    img_i = text_i = side_i = 0
    sidebars = [c for c in IMG_ROTATION if c[0] == "Sidebar Portrait"]
    for r in section:
        if r.origin != "auto":
            prev = (r.archetype, r.zone)
            continue

        def fits(archetype: str) -> bool:
            return holds_at_full_type(r, archetype) and (
                not r.has_image or not photo_fit(r, archetype).problem)

        choice: tuple[str, str] | None = None
        if r.has_image:
            choice, side_i = _rotate(sidebars, side_i, fits, prev)
            if choice is None:
                choice, img_i = _rotate(IMG_ROTATION, img_i, fits, prev)
            if choice is None:
                # No frame suits the photo: the band or hero that shows the most
                # of the food. A failing sidebar only when neither holds the
                # text — a column that misses the food is the worst crop there
                # is, but a second page for a one-page recipe is worse.
                open_to = [c for c in IMG_ROTATION
                           if PHOTO_FRAMES[c[0]][3] != "column" and holds_at_full_type(r, c[0])]
                open_to = open_to or [c for c in sidebars if holds_at_full_type(r, c[0])]
                shown = {a: photo_fit(r, a).shown for a, _ in open_to}
                if shown:
                    best = [c for c in open_to if c[0] == max(shown, key=shown.get)]
                    choice = next((c for c in best if c != prev), best[0])
        elif not r.ingredients and not r.directions:
            choice = ("Text-Only Framed", "prose")
        else:
            choice, text_i = _rotate(TEXT_ROTATION, text_i, fits, prev)
        if choice is None:
            fits_leaf = r.has_image and fits(TWO_PAGE_SPREAD[0])
            choice = TWO_PAGE_SPREAD if fits_leaf else RECIPE_SPREAD
        r.archetype, r.zone = choice
        prev = (r.archetype, r.zone)
    return prev


def assemble_recipes() -> list[Recipe]:
    recipes = enumerate_recipes()
    for r in recipes:
        if r.is_generated:
            continue  # no markdown; generated_page() set everything it needs
        parse_recipe(r)
        if r.is_divider or r.is_chapter_page:
            # A chapter's page takes its heading from book.yaml, which is also
            # what the table of contents prints, so the two cannot disagree.
            key = r.slug if r.is_divider else r.category
            r.title = CATEGORY_LABELS.get(key, key.replace("-", " ").title())
        if r.is_divider:
            # Fixed archetype, not part of the auto-rotation — a divider is always
            # a plain centered title page, never chosen for photo/text variety.
            # A one-page chapter is ordinary content and stays in the rotation.
            r.archetype, r.zone, r.origin = "Text-Only Framed", "divider", "fixed"
    # Generated pages are not in the rotation, so they cannot shift its pattern.
    from itertools import groupby
    prev: tuple[str, str] = ("", "")
    content = (r for r in recipes if not r.is_generated)
    for _, group in groupby(content, key=lambda r: r.category):
        prev = assign_section(list(group), prev)
    return recipes


# Shrink any page whose content would spill past the bottom safe margin, so
# nothing is ever clipped. Runs on load (and before Print -> PDF). Full-bleed
# Hero pages are exempt — their panel intentionally reaches the trim.
#
# First, flow() lays out every Recipe Spread by measurement, so the zoom pass
# sees its final pages. Python cannot know where a column breaks, so the text
# arrives whole in the verso's first column and is distributed here:
#   - the flow's pieces are list items, one step, ingredient, or note each — never
#     split — with a section heading or ingredient subhead glued to the item
#     after it, so neither ever ends a column;
#   - the verso's two columns are filled in reading order (ingredients, then
#     directions, then notes), each as far as it holds;
#   - the rest goes to the recto, split between its two columns where the
#     taller is shortest, so the text ends level;
#   - the photograph takes the height left under the recto's columns. If that is
#     under MIN_PHOTO it becomes a band under the verso's title block instead,
#     and the text is flowed again around it.
# Each run starts from scratch, so fonts or images arriving late change nothing.
#
# Then splitIngredients() settles each Two-Page Spread recipe page: its
# ingredients sit in one narrow column unless the page cannot hold them at full
# size, in which case the wider two-sub-column setting is tried and kept if it
# needs less room.
FIT_SCRIPT = """
<script>
(function () {
  var MIN_PHOTO = 2.5 * 96;  // 2.5in in CSS px: the smallest recto photo worth printing
  var slice = Array.prototype.slice;

  function readUnits(col) {
    var units = [];
    slice.call(col.children).forEach(function (block) {
      var list = block.querySelector('ul, ol'), head = block.querySelector('.sec');
      var pending = [], n = 0;
      slice.call(list.children).forEach(function (li) {
        pending.push(li);
        if (li.classList.contains('subhead')) return;
        n += 1;
        units.push({block: block.className, list: list.tagName, cls: list.className,
                    head: head, items: pending, n: n});
        head = null;
        pending = [];
      });
    });
    return units;
  }

  // Rebuild a column from units: consecutive units of one list share a block;
  // a block continued from an earlier column carries no heading, and a
  // continued list of steps keeps its numbering.
  function fill(col, units) {
    col.textContent = '';
    var list = null, cls = null;
    units.forEach(function (u) {
      if (u.cls !== cls) {
        cls = u.cls;
        var block = document.createElement('div');
        block.className = u.block;
        if (u.head) block.appendChild(u.head);
        list = document.createElement(u.list);
        list.className = u.cls;
        if (u.list === 'OL') list.start = u.n;
        block.appendChild(list);
        col.appendChild(block);
      }
      u.items.forEach(function (li) { list.appendChild(li); });
    });
  }

  function place(units, cols) {
    var k = 0;
    [cols[0], cols[1]].forEach(function (col) {
      var from = k;
      while (k < units.length) {
        fill(col, units.slice(from, k + 1));
        if (col.scrollHeight > col.clientHeight + 1) break;
        k += 1;
      }
      fill(col, units.slice(from, k));
    });
    var rest = units.slice(k), best = rest.length, bestH = Infinity;
    for (var j = rest.length; j >= 0; j--) {  // on a tie, the left column runs longer
      fill(cols[2], rest.slice(0, j));
      fill(cols[3], rest.slice(j));
      var h = Math.max(cols[2].offsetHeight, cols[3].offsetHeight);
      if (h < bestH - 0.5) { bestH = h; best = j; }
    }
    fill(cols[2], rest.slice(0, best));
    fill(cols[3], rest.slice(best));
  }

  function flow() {
    document.querySelectorAll('.rs--verso').forEach(function (verso) {
      var vpage = verso.closest('.page'), rpage = vpage.nextElementSibling;
      var recto = rpage.querySelector('.rs--recto');
      [vpage, rpage].forEach(function (p) { p.querySelector('.page-inner').style.zoom = ''; });
      var cols = slice.call(verso.querySelectorAll('.rs-col'))
        .concat(slice.call(recto.querySelectorAll('.rs-col')));
      if (!verso.rsUnits) {
        verso.rsUnits = readUnits(cols[0]);
        verso.rsPhoto = recto.querySelector('.rs-photo');
      }
      var photo = verso.rsPhoto;
      if (photo) {
        photo.classList.remove('rs-photo--band');
        recto.appendChild(photo);
      }
      place(verso.rsUnits, cols);
      if (photo && photo.getBoundingClientRect().height < MIN_PHOTO) {
        photo.classList.add('rs-photo--band');
        verso.insertBefore(photo, verso.querySelector('.rs-cols'));
        place(verso.rsUnits, cols);
      }
    });
  }

  // A prose page too long for one leaf (prose_continues()) continues on the
  // next: fill the first frame block by block, and split the block that no
  // longer fits — a paragraph at a line boundary, a list between items —
  // leaving at least two lines (two items) on each side; a heading stays with
  // what follows it. Rebuilt from the original blocks on every run.
  function textNodes(el) {
    var out = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), n;
    while ((n = w.nextNode())) out.push(n);
    return out;
  }
  function wordCount(p) {
    return textNodes(p).reduce(function (n, t) { return n + (t.data.match(/\\S+/g) || []).length; }, 0);
  }
  // A copy of paragraph p holding only its first k words (head) or the rest
  // (tail), inline markup kept on both sides.
  function cutWords(p, k, head) {
    var c = p.cloneNode(true), seen = 0;
    textNodes(c).forEach(function (t) {
      t.data = t.data.split(/(\\s+)/).filter(function (s) {
        if (!s) return false;
        if (/\\S/.test(s)) { var i = seen++; return head ? i < k : i >= k; }
        return head ? seen < k : seen > k;
      }).join('');
    });
    return c;
  }
  function lineCount(el) {
    return Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
  }
  function flowProse() {
    document.querySelectorAll('.prose[data-continues]').forEach(function (src) {
      var page = src.closest('.page'), next = page.nextElementSibling;
      var dst = next && next.querySelector('.prose--cont');
      if (!dst) return;
      [page, next].forEach(function (p) { p.querySelector('.page-inner').style.zoom = ''; });
      if (!src.proseBlocks) src.proseBlocks = slice.call(src.children);
      var frame = src.closest('.textonly'), inner = page.querySelector('.page-inner');
      function fits() {  // against the page, not the frame, which grows with its text
        var cs = getComputedStyle(frame);
        return src.getBoundingClientRect().bottom <= inner.getBoundingClientRect().bottom
          - parseFloat(cs.paddingBottom) - parseFloat(cs.borderBottomWidth);
      }
      function trial(el) { src.appendChild(el); var ok = fits(); src.removeChild(el); return ok; }
      function splitPara(p) {
        var lo = 0, hi = wordCount(p);
        while (lo < hi) {
          var mid = Math.ceil((lo + hi) / 2);
          if (trial(cutWords(p, mid, true))) lo = mid; else hi = mid - 1;
        }
        var k = lo;
        while (k > 0) {
          var head = cutWords(p, k, true), tail = cutWords(p, k, false);
          src.appendChild(head); dst.insertBefore(tail, dst.firstChild);
          var hl = lineCount(head), tl = lineCount(tail);
          src.removeChild(head); dst.removeChild(tail);
          if (hl < 2) return null;
          if (tl >= 2) { tail.classList.add('prose-cont'); return [head, tail]; }
          // widow: carry the head's last line over to the next page
          while (k > 0) {
            head = cutWords(p, --k, true);
            src.appendChild(head); var l = lineCount(head); src.removeChild(head);
            if (l < hl) break;
          }
        }
        return null;
      }
      function splitList(ul) {
        var items = slice.call(ul.children), i = 0;
        while (i < items.length) {
          var h = ul.cloneNode(false);
          items.slice(0, i + 1).forEach(function (li) { h.appendChild(li.cloneNode(true)); });
          if (!trial(h)) break;
          i += 1;
        }
        if (items.length - i === 1) i -= 1;
        if (i < 2) return null;
        var head = ul.cloneNode(false), tail = ul.cloneNode(false);
        items.forEach(function (li, j) { (j < i ? head : tail).appendChild(li.cloneNode(true)); });
        return [head, tail];
      }
      src.textContent = '';
      dst.textContent = '';
      var blocks = src.proseBlocks.map(function (b) { return b.cloneNode(true); });
      for (var i = 0; i < blocks.length; i++) {
        var b = blocks[i];
        src.appendChild(b);
        if (fits()) continue;
        src.removeChild(b);
        var parts = b.tagName === 'P' ? splitPara(b) : b.tagName === 'UL' ? splitList(b) : null;
        var rest = parts ? [parts[1]] : [b];
        if (parts) src.appendChild(parts[0]);
        var last = src.lastElementChild;
        if (!parts && last && /prose-(heading|rule)/.test(last.className)) {
          src.removeChild(last);
          rest.unshift(last);
        }
        rest.concat(blocks.slice(i + 1)).forEach(function (r) { dst.appendChild(r); });
        break;
      }
    });
  }

  // How far below its own top a target's content reaches.
  function extent(target) {
    var top = target.getBoundingClientRect().top, reach = 0;
    target.querySelectorAll('*').forEach(function (el) {
      var b = el.getBoundingClientRect().bottom - top;
      if (b > reach) reach = b;
    });
    return reach;
  }

  function splitIngredients() {
    document.querySelectorAll('.two-col--spread').forEach(function (cols) {
      var inner = cols.closest('.page-inner');
      inner.style.zoom = '';
      cols.classList.remove('two-col--split');
      var single = extent(inner);
      if (single <= inner.clientHeight + 1) return;
      cols.classList.add('two-col--split');
      if (extent(inner) >= single) cols.classList.remove('two-col--split');
    });
  }

  // Frame each band photo once its box has its final size: the window
  // band_windows() cut for the height nearest the box's shape, cropped to with
  // object-view-box and covering the box.
  function framePhotos() {
    document.querySelectorAll('.photo[data-windows]').forEach(function (box) {
      var W = box.clientWidth, H = box.clientHeight;
      if (!W || !H) return;
      var shape = W / H, win = null;
      box.dataset.windows.split(';').forEach(function (s) {
        var v = s.split(',').map(Number);
        if (!win || Math.abs(v[0] - shape) < Math.abs(win[0] - shape)) win = v;
      });
      var pct = function (v) { return (v * 100).toFixed(2) + '%'; };
      box.firstElementChild.style.objectViewBox = 'inset(' + pct(win[2]) + ' ' + pct(1 - win[3]) + ' '
        + pct(1 - win[4]) + ' ' + pct(win[1]) + ')';
    });
  }

  function fit() {
    flow();
    flowProse();
    splitIngredients();
    document.querySelectorAll('.page').forEach(function (p) {
      var target, avail;
      if (p.classList.contains('page--nopad')) {
        // Hero pages: zoom the panel's content wrapper. Zooming .page-inner
        // would shrink the full-bleed photo too.
        target = p.querySelector('.hero-body');
        if (!target) return;
        var panel = target.parentElement;
        target.style.zoom = '';
        avail = p.getBoundingClientRect().bottom
              - parseFloat(getComputedStyle(panel).paddingBottom)
              - target.getBoundingClientRect().top;
      } else {
        target = p.querySelector('.page-inner');
        if (!target) return;  // blank leaves have no inner
        target.style.zoom = '';
        avail = target.clientHeight;
      }
      var need = extent(target);
      // A pixel of slack: flex-stretched columns end exactly at the bottom, and
      // sub-pixel rounding must not cost a full page a 0.985 zoom.
      if (need > avail + 1) target.style.zoom = Math.max(0.52, (avail / need) * 0.985).toFixed(3);
    });
    framePhotos();
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit); else window.addEventListener('load', fit);
  window.addEventListener('load', fit);  // re-run once images have loaded
  window.addEventListener('beforeprint', fit);
})();
</script>
"""


# The zone of a blank leaf padding a short book to the hardcover minimum. A
# blank prints no zone; this only lets the build summary count the padding.
PADDING = "padding"


def _blank(zone: str = "") -> Recipe:
    return Recipe(category="_blank", slug="_blank", archetype="", zone=zone, origin="fixed", is_blank=True)


def expand_two_page(pages: list[Recipe]) -> list[Recipe]:
    """Turn each two-leaf recipe into the two leaves it actually prints as.

    Two-Page Spread: a full-bleed photo on the verso, the recipe on the facing
    recto. Recipe Spread: the verso is the entry itself (title block and the
    first columns of text, so its page number is the recipe's); the recto
    carries the rest of the text and the photograph.

    The extra leaf is a copy of the recipe rather than a new kind of object, so
    it inherits the accent, folder, and image without a parallel code path; only
    `is_spread_photo` / `is_spread_cont` distinguishes it. A Two-Page Spread with
    no photograph on disk collapses back to a single recipe page — the archetype
    asks for a facing photo, and half a spread is worse than none.

    A prose page too long for one leaf at full size (prose_continues()) is
    followed by its continuation leaf, `is_prose_cont`, on the next page; the
    two need not face each other. Any inset stays on the first leaf."""
    out: list[Recipe] = []
    for r in pages:
        if prose_continues(r):
            out.append(r)
            out.append(replace(r, is_prose_cont=True, zone="prose (continued)", extras=[]))
            continue
        if r.archetype == "Two-Page Spread" and r.has_image:
            out.append(replace(r, is_spread_photo=True, zone="photo (verso)"))
            out.append(replace(r, zone="recipe (recto)"))
        elif r.archetype == "Recipe Spread":
            out.append(replace(r, zone="title + text (verso)"))
            out.append(replace(r, is_spread_cont=True, zone="text + photo (recto)"))
        else:
            out.append(r)
    return out


def _opens_pair(r: Recipe) -> bool:
    """The verso leaf of a two-leaf recipe, which must land on an even page."""
    return r.is_spread_photo or (r.archetype == "Recipe Spread" and not r.is_spread_cont)


def _borrowable(queue: list[Recipe], after: int, category: str) -> int | None:
    """Index of the first ordinary single page following a two-leaf recipe that
    can be lifted in front of it to fill a parity gap, or None.

    It has to be a plain one-page entry from the SAME chapter: pulling one
    across a divider would move a recipe into a chapter it does not belong to,
    lifting half of another pair would separate its two leaves, and lifting an
    entry followed by its keepsake page would leave the keepsake behind."""
    for j in range(after, len(queue)):
        r = queue[j]
        if r.is_divider:
            break  # reached the next chapter; nothing here belongs to this one
        if r.category != category:
            break
        if r.is_blank or r.is_generated or r.is_chapter_page or r.is_keepsake:
            continue
        if r.archetype in ("Two-Page Spread", "Recipe Spread"):
            continue
        if j + 1 < len(queue) and queue[j + 1].is_keepsake:
            continue
        return j
    return None


def insert_recto_blanks(pages: list[Recipe]) -> list[Recipe]:
    """Force every section divider onto a recto (right-hand, odd) page, and
    every two-leaf recipe's first leaf onto a verso so the second faces it.
    Then pad to an even total so the book binds correctly.

    A divider landing wrong can only be fixed with a blank leaf: the slot before
    it belongs to the previous chapter, and the only pages available to fill it
    come from the next one. A pair is different — the pages after it are its
    own chapter-mates, so instead of printing an empty leaf mid-chapter we lift
    the next ordinary recipe in front of the pair. That costs a departure from
    the chapter's alphabetical order and saves the reader a blank page."""
    queue = list(pages)
    out: list[Recipe] = []
    i = 0
    while i < len(queue):
        r = queue[i]
        next_slot = len(out) + 1
        if r.is_divider and next_slot % 2 == 0:  # next slot is a verso
            out.append(_blank())
        elif _opens_pair(r) and next_slot % 2 == 1:  # next slot is a recto
            # The pair occupies i and i+1, so look from i+2 on.
            j = _borrowable(queue, i + 2, r.category)
            out.append(queue.pop(j) if j is not None else _blank())
        out.append(r)
        i += 1
    if len(out) % 2 == 1:
        out.append(_blank())
    return out


def build(recipes: list[Recipe]) -> tuple[str, list[Recipe]]:
    # Keepsake leaves are placed first, so expansion and print parity see them
    # in their final position right after the entry they belong to. Generated
    # pages already sit at their place in book.yaml's chapters list; a focused
    # --only build leaves them out, since they describe the whole book.
    body = expand_two_page(place_extras([
        r for r in recipes if not ONLY or (r.slug in ONLY and not r.is_generated)
    ]))

    # The contents, contributors, and index take as many leaves as their rows
    # need, and their rows carry page numbers that depend on how many leaves
    # they take. So: lay the book out with a leaf count per reference chapter
    # (one to start), number it, paginate, and go again if any count changed.
    # A row's height does not depend on the number in it, so this settles on
    # the second pass.
    leaf_counts: dict[str, int] = {}
    for _ in range(5):
        shown = expand_reference_pages(body, leaf_counts)
        # Both builds paginate as the bound book does — recto openers, pairs
        # starting on a verso — so the screen draft, laid out in spreads, shows
        # every page beside the page it faces. A focused --only build too: a
        # two-page recipe there is still shown as its spread.
        shown = insert_recto_blanks(shown)
        # Lulu binds no hardcover thinner than its minimum, so a short book is
        # padded with blank leaves at the back. A focused build is not a book.
        if not ONLY:
            shown += [_blank(PADDING) for _ in range(LULU_HARDCOVER_MIN_PAGES - len(shown))]
        for i, r in enumerate(shown, start=1):
            r.page_number = i
        present = {r.category for r in shown if r.is_generated}
        laid_out = {name: paginate(groups(shown))
                    for name, groups in REFERENCE_GROUPS.items() if name in present}
        counts = {name: len(leaves) for name, leaves in laid_out.items()}
        if counts == leaf_counts:
            break
        leaf_counts = counts
    else:
        raise RuntimeError(f"reference pages never settled on a leaf count: {leaf_counts}")

    leaves = {name: iter(pages) for name, pages in laid_out.items()}
    for r in shown:
        if r.is_generated and r.category in leaves:
            r.columns = next(leaves[r.category])

    pages = "\n".join(render_page(r) for r in shown)
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{esc(CONFIG.title if PRINT else CONFIG.title + ' — Draft')}</title>"
        f"<style>{mode_vars_css()}{font_face_css()}{CSS}</style></head>"
        f"<body><div class='book'>{pages}</div>"
        f"{FIT_SCRIPT}</body></html>"
    )
    return html, shown


def main(print_mode: bool = False, only: set[str] | None = None) -> None:
    global PRINT, ONLY
    PRINT, ONLY = print_mode, set(only or ())
    out = (BOOK_ROOT.draft / "cookbook-print.html") if PRINT else OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    recipes = assemble_recipes()
    html, shown = build(recipes)
    out.write_text(html, encoding="utf-8", newline="\n")
    origins = Counter(r.origin for r in shown)
    # A two-page recipe is one photograph on two leaves; count the recipe, not
    # the pages. A keepsake leaf is a copy of its entry and shows the extras,
    # not the photo.
    with_img = sum(1 for r in shown if r.has_image
                   and not (r.is_spread_photo or r.is_spread_cont or r.is_keepsake))
    print(f"Wrote {out.relative_to(ROOT)}")
    print(f"Pages: {len(shown)}  (curated: {origins['curated']}, fixed: {origins['fixed']}, "
          f"auto: {origins['auto']}, with image: {with_img})")
    for arch, n in Counter("blank" if r.is_blank else r.archetype for r in shown).most_common():
        print(f"  {n:3d}  {arch}")
    padding = sum(1 for r in shown if r.is_blank and r.zone == PADDING)
    if padding:
        print(f"Added {padding} blank page{'s' if padding > 1 else ''} at the back: Lulu binds "
              f"no hardcover under {LULU_HARDCOVER_MIN_PAGES} pages. More entries fill them.")
    needed = lulu_inside_margin(len(shown))
    if not ONLY and needed > PRINT_INSIDE_MARGIN_IN:
        print(f"WARNING: {len(shown)} pages needs a {needed} in inside margin for Lulu binding; "
              f"the print build uses {PRINT_INSIDE_MARGIN_IN} in. Open an issue at "
              "https://github.com/scanady/family-cookbook/issues before printing a book this long.",
              file=sys.stderr)
