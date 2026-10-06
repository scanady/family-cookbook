"""`cookbook ingest`: recipe cards and pages in, book entries out.

Two model calls per recipe, as the ingest skill does it by hand:

1. Transcribe. The pages of one source go to a vision model in order, a window
   at a time. It returns every entry verbatim, joined across page breaks, with
   the pages it spans and whether it looks cut off. An entry that touches the
   last page of a window is read again at the start of the next window, so a
   recipe that runs onto the following page is never split.
2. Normalize. Each recipe's verbatim text goes to the model with the book's
   recipe rules (the same instruction files the agent skills ship), and comes
   back as fields. The engine writes recipe.md from the fields, so the format
   is the engine's, not the model's.

Then a check the model cannot talk its way past: every number in an
ingredient, the yield, and the temperature must appear in the source. Anything
else is reported as possibly invented, by recipe, for a person to check.

Writes book/recipes/{chapter}/{slug}/ with recipe.md, sources/recipe-original.md,
and the page images, and appends each recipe's token use and cost to
book/sources/ai-log.jsonl. Non-recipe entries are reported, not written.

Without an API key it warns and does the part that needs no model: the pages
become one recipe folder with the original kept, and a recipe.md for a person
to type up beside it.
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from . import config, models

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
PDF_DPI = 200      # a PDF page rasterized for reading: small type stays legible
WINDOW = 6         # pages per transcription call
# The command that installs poppler (pdftoppm, pdftotext, pdfimages, pdfinfo).
POPPLER_INSTALL = ("winget install -e --id oschwartz10612.Poppler" if sys.platform == "win32" else
                   "brew install poppler" if sys.platform == "darwin" else "sudo apt install poppler-utils")
# Word's Symbol and Wingdings fonts put their characters in the private-use
# block, U+F020-U+F0FF, at U+F000 plus the Latin-1 code (U+F0B0 is °): read them
# as the characters they draw.
SYMBOL_FONT = {code: code - 0xF000 for code in range(0xF020, 0xF100)}

TRANSCRIBE_PROMPT = """\
You are an archivist transcribing family recipe documents for a printed family
cookbook. The images above are the pages of one source, in order.

List every entry on these pages in reading order. An entry is one recipe, or
one piece of non-recipe writing (a note, a story, a poem, a household tip, a
dedication). Ignore page furniture: running headers and footers, page numbers,
a chapter title that only labels the page, a table of contents, blank pages.

For each entry:
- verbatim: the entry exactly as written. Keep line breaks, spelling,
  capitalization, abbreviations, punctuation, symbols such as ½ and °, order,
  and marginalia. Do not correct, complete, or reformat anything. Write
  [illegible] for a word you cannot read, and your best reading followed by
  [?] for one you are unsure of.
- An entry that continues across a page break is ONE entry. Join its parts in
  reading order and leave out the headers, footers, and page numbers between
  them. The same holds when it is marked "continued", "over", or "see back",
  or when the next page simply picks up mid-sentence or mid-list. Text at the
  top of a page, before any title, continues the entry that ended the page
  before it.
- pages: the page numbers it appears on.
- complete: false when the entry looks cut off: it ends mid-sentence or
  mid-list, a recipe has ingredients but no method (or a method but no
  ingredients), it points to a page not given, or the first page starts partway
  through it. Say why in incomplete_reason; leave that empty when complete.
- kind: "recipe" for something you cook or mix, food or drink; "other" for
  everything else, including a joke written in the form of a recipe.
- title: as written. If the entry has none, a short description in square
  brackets.
"""

# Added to the prompt when a PDF page carries text: a typed document's text
# layer is exact where a reading of the picture can mistake ¼ for ¾.
TEXT_LAYER_PROMPT = """
Some pages also carry the document's own text layer, given below by page
number. Where a page has one, take every character from it (numbers,
fractions, symbols, spelling) and use the image only for layout and reading
order, and for anything the text layer leaves out.
"""

TRANSCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": ["recipe", "other"]},
                    "pages": {"type": "array", "items": {"type": "integer"}},
                    "verbatim": {"type": "string"},
                    "complete": {"type": "boolean"},
                    "incomplete_reason": {"type": "string"},
                },
                "required": ["title", "kind", "pages", "verbatim", "complete", "incomplete_reason"],
            },
        }
    },
    "required": ["entries"],
}

NORMALIZE_PROMPT = """\
You are an archivist turning one verbatim recipe transcription into a family
cookbook's clean entry. Fidelity first, format second.

{cardinal_rule}

The book's recipe rules follow. You return fields, not markdown: the engine
writes recipe.md from them, so ignore the rules about files, folders, photos,
and links, and follow the ones about content.

{recipe_rules}

The fields:
- title: the recipe's title as the source gives it, without a trailing period.
  Supply a short plain title only when the source has none, and say so in
  judgment_calls.
- cook: the person the source credits ("From the kitchen of ...", a signature,
  "Ruth's ..."), or "" when it names no one. Never guess.
- chapter: the name of the chapter this recipe belongs in, from this list
  (name: label): {chapters}
- cuisine: the regional or national cuisine when the recipe makes it plain
  ("New England", "Italian"), else "Not specified".
- yield, prep_time, cook_time, temperature: as the source states them, else
  "Not specified". Write a temperature as 350°F. Prep time only when the source
  gives one.
- chill_time, total_time: only when the source states one, else "".
- ingredient_groups: the main list with heading "", then each named
  sub-recipe ("Frosting", "Sauce") as its own group. Each item keeps the
  source's amount, unit, ingredient, and preparation, normalized in form only:
  ASCII fractions (1/2, 1 3/4), lowercase plural units (cups, teaspoons,
  sticks), common words in lowercase (eggs, flour) and names in capitals
  (Bisquick, Eagle brand), no trailing period. An ingredient the source names
  without an amount stays without one. Do not split one listed ingredient into
  several. When the source has its own ingredient list, an ingredient it
  mentions only in its method stays only in the method. When the source has no
  list (a recipe written as a paragraph or a story), list every ingredient the
  text names, in the order it names them, with only the amounts it gives: the
  list is never empty for a recipe that names any ingredient.
- directions: the method in order, one action or short group of actions per
  step, in the source's words. Keep its references as written ("mix above
  ingredients", "the mixture"); do not replace them with ingredient names.
  Fold a phase name into the step ("For the sauce, melt ..."). No numbering in
  the strings.
- notes: stories, tips, serving suggestions, and variations from the source,
  in its words.
- judgment_calls: every place you had to interpret: an unclear word, an
  ambiguous amount, a title you supplied, a sentence you moved to notes. Short.

The verbatim transcription:

{verbatim}
"""

NORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "cook": {"type": "string"},
        "chapter": {"type": "string"},
        "cuisine": {"type": "string"},
        "yield": {"type": "string"},
        "prep_time": {"type": "string"},
        "cook_time": {"type": "string"},
        "temperature": {"type": "string"},
        "chill_time": {"type": "string"},
        "total_time": {"type": "string"},
        "ingredient_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "items"],
            },
        },
        "directions": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
        "judgment_calls": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title", "cook", "chapter", "cuisine", "yield", "prep_time", "cook_time", "temperature",
        "chill_time", "total_time", "ingredient_groups", "directions", "notes", "judgment_calls",
    ],
}

# recipe.md metadata, in order: (field, label, always written). Always-written
# fields say "Not specified" rather than disappear, as the book's recipes do.
METADATA = [
    ("cuisine", "Cuisine", True),
    ("yield", "Yield", True),
    ("prep_time", "Prep time", True),
    ("cook_time", "Cook time", True),
    ("temperature", "Temperature", True),
    ("chill_time", "Chill time", False),
    ("total_time", "Total time", False),
]


@dataclass
class Page:
    image: Path    # the image the model reads and sources/ keeps
    label: str     # where it came from, for people: "card.jpg", "book.pdf p. 65"
    text: str = ""  # a PDF page's own text layer, when it has one


@dataclass
class Entry:
    title: str
    kind: str
    pages: list[int]          # 1-based, across all input pages
    verbatim: str
    complete: bool
    incomplete_reason: str
    usage: models.Usage = models.NO_USAGE


@dataclass
class Result:
    entry: Entry
    folder: Path | None = None
    recipe_md: str = ""
    warnings: list[str] = field(default_factory=list)
    judgment_calls: list[str] = field(default_factory=list)
    usage: models.Usage = models.NO_USAGE


# ---- pages ------------------------------------------------------------------

def expand(paths: list[Path], tmp: Path) -> list[Page]:
    """The input files as pages in order; a PDF becomes one image per page."""
    pages: list[Page] = []
    for path in paths:
        suffix = path.suffix.lower()
        if not path.is_file():
            raise SystemExit(f"{path}: no such file")
        if suffix in IMAGE_TYPES:
            pages.append(Page(path, path.name))
        elif suffix == ".pdf":
            for tool in ("pdftoppm", "pdftotext", "pdfimages", "pdfinfo"):
                if not shutil.which(tool):
                    raise SystemExit(f"{tool} is not installed — it reads PDF pages; install poppler: "
                                     f"{POPPLER_INSTALL}")
            prefix = tmp / f"{len(pages):03d}-{path.stem}"
            subprocess.run(["pdftoppm", "-r", str(PDF_DPI), "-jpeg", "-jpegopt", "quality=88",
                            str(path), str(prefix)], check=True)
            texts = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True,
                                   encoding="utf-8", errors="replace").stdout.translate(SYMBOL_FONT).split("\f")
            scans = scanned_pages(path)
            for n, image in enumerate(sorted(tmp.glob(f"{prefix.name}-*.jpg")), 1):
                # A scanned page's text is OCR, not the document's own: often
                # wrong, so the model reads the picture, as it does a photo.
                text = texts[n - 1].strip() if n <= len(texts) and n not in scans else ""
                pages.append(Page(image, f"{path.name} p. {n}", text))
        else:
            raise SystemExit(f"{path}: not a page image or PDF ({', '.join(sorted(IMAGE_TYPES))}, .pdf)")
    return pages


SCAN_COVER = 0.8  # an image covering this share of a page makes the page a scan


def scanned_pages(pdf: Path) -> set[int]:
    """The pages of a PDF that are pictures of paper: one image covers the page,
    so any text layer on them was added by OCR."""
    info = subprocess.run(["pdfinfo", "-f", "1", "-l", "100000", str(pdf)], check=True,
                          capture_output=True, encoding="utf-8", errors="replace").stdout
    sizes = {int(n): float(w) * float(h) / 72 / 72
             for n, w, h in re.findall(r"^Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+)", info, flags=re.M)}
    listing = subprocess.run(["pdfimages", "-list", str(pdf)], check=True, capture_output=True,
                             encoding="utf-8", errors="replace").stdout
    scans = set()
    for line in listing.splitlines()[2:]:
        cols = line.split()
        if len(cols) < 14 or cols[2] not in ("image", "smask") or not cols[0].isdigit():
            continue
        page, width, height, xppi, yppi = int(cols[0]), int(cols[3]), int(cols[4]), int(cols[12]), int(cols[13])
        area = sizes.get(page) or next(iter(sizes.values()), 0)
        if area and xppi and yppi and (width / xppi) * (height / yppi) >= SCAN_COVER * area:
            scans.add(page)
    return scans


def select(pages: list[Page], spec: str) -> list[tuple[int, Page]]:
    """Pages chosen by a "3", "3-5", or "1,4-6" spec, with their 1-based numbers."""
    numbered = list(enumerate(pages, 1))
    if not spec:
        return numbered
    wanted: set[int] = set()
    for part in spec.split(","):
        first, _, last = part.strip().partition("-")
        try:
            wanted.update(range(int(first), int(last or first) + 1))
        except ValueError:
            raise SystemExit(f"--pages {spec!r}: use page numbers like 3, 3-5, or 1,4-6") from None
    chosen = [(n, p) for n, p in numbered if n in wanted]
    if not chosen:
        raise SystemExit(f"--pages {spec!r} selects none of the {len(pages)} pages")
    return chosen


# ---- step 1: transcribe -------------------------------------------------------

def transcribe(model: models.Model, pages: list[tuple[int, Page]]) -> tuple[list[Entry], list[int]]:
    """Every entry on the pages, verbatim, joined across page breaks; and the
    pages the model would not read.

    Pages go to the model WINDOW at a time. When a window is not the last, any
    entry on its final page may continue past it, so the next window restarts
    at the earliest first page of those entries, and this window keeps only the
    entries that end before that page: everything from it on is read again,
    whole, in the next window. A window whose every entry runs to its end is
    widened instead.

    A model can refuse a window (a recitation filter on a published book, most
    often). The window then shrinks a page at a time until the model reads it,
    so the pages it will read stay together and their joins survive; it is not
    widened again. A page refused on its own is skipped and returned, so one
    page does not cost the rest of the run."""
    position = {n: i for i, (n, _) in enumerate(pages)}
    entries: list[Entry] = []
    unread: list[int] = []
    spent = models.NO_USAGE  # every call, including windows read again
    start = 0
    while start < len(pages):
        end = min(start + WINDOW, len(pages))
        narrowed = False
        found: list[Entry] | None = None
        while True:
            window = pages[start:end]
            prompt = TRANSCRIBE_PROMPT
            layers = [(i, p.text) for i, (_, p) in enumerate(window, 1) if p.text]
            if layers:
                prompt += TEXT_LAYER_PROMPT + "".join(f"\nPage {i} text layer:\n{text}\n" for i, text in layers)
            try:
                answer, usage = model.json(prompt, TRANSCRIBE_SCHEMA, [p.image for _, p in window])
            except models.Refused:
                if len(window) > 1:
                    end, narrowed = end - 1, True
                    continue
                unread.append(window[0][0])
                break
            found = [
                Entry(e["title"], e["kind"], sorted({window[i - 1][0] for i in e["pages"] if 1 <= i <= len(window)}),
                      e["verbatim"].strip("\n"), e["complete"], e["incomplete_reason"])
                for e in answer["entries"]
            ]
            found = [e for e in found if e.pages and e.verbatim.strip()]
            spent = spent + usage
            restart = end
            if end < len(pages) and not narrowed:
                at_end = [e for e in found if e.pages[-1] == window[-1][0]]
                if at_end:
                    restart = min(position[e.pages[0]] for e in at_end)
            if restart == start:
                if narrowed:  # the window cannot grow back into a refused page
                    restart = end
                    break
                end = min(end + WINDOW, len(pages))
                continue
            break
        if found is None:
            start += 1
            continue
        entries += [e for e in found if position[e.pages[-1]] < restart]
        start = restart
    for e in entries:
        e.usage = spent.share(len(entries))
    return entries, unread


# ---- step 2: normalize --------------------------------------------------------

def _agent_file(*parts: str) -> str:
    return resources.files("family_cookbook").joinpath("agent_files", *parts).read_text(encoding="utf-8")


def _without_frontmatter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
    if not match:
        raise SystemExit(f"the ingest skill has no '## {heading}' section — reinstall the engine")
    return match.group(1).strip()


def normalize_prompt(verbatim: str, chapters: list[config.Chapter]) -> str:
    skill = _agent_file("skills", "cookbook-recipe-ingest", "SKILL.md")
    rules = _without_frontmatter(_agent_file("instructions", "recipe-content.instructions.md"))
    return NORMALIZE_PROMPT.format(
        cardinal_rule=_section(skill, "The Cardinal Rule"),
        recipe_rules=rules,
        chapters="; ".join(f"{c.name}: {c.label}" for c in chapters),
        verbatim=verbatim,
    )


def recipe_markdown(fields: dict, chapter: config.Chapter, cook: str, linked_source: bool) -> str:
    lines = [f"# {fields['title'].strip()}", ""]
    if cook:
        lines += [f"*{cook}*", ""]
    lines.append(f"- **Category:** {chapter.label}")
    for key, label, always in METADATA:
        value = " ".join(fields.get(key, "").split())
        if value or always:
            lines.append(f"- **{label}:** {value or 'Not specified'}")
    lines += ["", "## Ingredients", ""]
    for group in fields["ingredient_groups"]:
        items = [i.strip().rstrip(".") for i in group["items"] if i.strip()]
        if not items:
            continue
        heading = group["heading"].strip().rstrip(":")
        if heading:
            if lines[-1] != "":
                lines.append("")
            lines.append(f"**{heading}:**")
        lines += [f"- {i}" for i in items]
    lines += ["", "## Directions", ""]
    lines += [f"{n}. {step.strip()}" for n, step in enumerate((s for s in fields["directions"] if s.strip()), 1)]
    notes = [n.strip() for n in fields["notes"] if n.strip()]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    if linked_source:
        lines += ["", "[View the original recipe](sources/recipe-original.md)"]
    return "\n".join(lines) + "\n"


def original_markdown(title: str, cook: str, verbatim: str, provenance: str, images: list[str]) -> str:
    lines = [f"# {title}", ""]
    if cook:
        lines += [f"*{cook}*", ""]
    lines += [provenance, ""]
    lines += [f"![Page {n}]({name})" for n, name in enumerate(images, 1)]
    if verbatim:
        body = verbatim.replace("```", "'''")  # a fence inside would end the block render.py reads
        lines += ["", "## Original Recipe", "", "```text", body, "```"]
    lines += ["", "[View the updated recipe](../recipe.md)"]
    return "\n".join(lines) + "\n"


def keep_pages(sources: Path, pages: list[Page]) -> list[str]:
    """Copy the pages into sources/ as original-1.jpg, original-2.png, …"""
    sources.mkdir(parents=True)
    names: list[str] = []
    for page in pages:
        name = f"original-{len(names) + 1}{page.image.suffix.lower()}"
        shutil.copyfile(page.image, sources / name)
        names.append(name)
    return names


def _today() -> str:
    today = dt.date.today()
    return f"{today:%B} {today.day}, {today.year}"


# ---- the check the model does not get a say in --------------------------------

UNICODE_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅕": "1/5", "⅖": "2/5", "⅗": "3/5",
    "⅘": "4/5", "⅙": "1/6", "⅚": "5/6", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}
# Longest first: "one-half" before "one", "a half" before "a".
NUMBER_WORDS = {
    "one-half": "1/2", "one-third": "1/3", "two-thirds": "2/3", "one-fourth": "1/4", "one-quarter": "1/4",
    "three-fourths": "3/4", "three-quarters": "3/4", "one-eighth": "1/8", "a half": "1/2", "half": "1/2",
    "quarter": "1/4", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "dozen": "12",
    "an": "1", "a": "1",
}
# A mixed number ("1 3/4") is one amount; a lone fraction or whole number is another.
AMOUNT = re.compile(r"\d+ \d+/\d+|\d+/\d+|\d+")


def _amounts(text: str, words: bool = False) -> list[str]:
    """The amounts in text as written, with fraction glyphs and "1-1/2" spelled
    "1 1/2"; with `words`, "two" and "half" count too."""
    text = text.lower().replace("⁄", "/")
    for glyph, ascii_ in UNICODE_FRACTIONS.items():
        text = text.replace(glyph, f" {ascii_}")
    if words:
        # "one and one-half" is one amount: "1 1/2"
        text = re.sub(r"\b(\w+)\s+and\s+(one-half|a half|one-quarter|one-fourth|three-fourths|three-quarters)\b",
                      lambda m: f"{m[1]} {m[2]}", text)
        for word, digits in NUMBER_WORDS.items():
            text = re.sub(rf"(?<![\w-]){word}(?![\w-])", f" {digits} ", text)
    text = re.sub(r"(\d)-(\d+/\d+)", r"\1 \2", text)
    return AMOUNT.findall(re.sub(r"[ \t]+", " ", text))


def _stated(text: str) -> set[str]:
    """Every amount a source states. A mixed number counts whole and by its
    parts, so a lone "3/4" matches the source's "1 3/4", but "8 3/4" does not
    match "8 1/4"."""
    found = set(_amounts(text, words=True))
    for amount in list(found):
        found.update(amount.split(" "))
    return found


def unsupported_numbers(verbatim: str, fields: dict) -> list[str]:
    """Amounts in the clean recipe that the source never states."""
    source = _stated(verbatim)
    problems = []
    checked = [("yield", fields["yield"]), ("temperature", fields["temperature"])]
    checked += [("ingredient", item) for g in fields["ingredient_groups"] for item in g["items"]]
    for where, text in checked:
        missing = [n for n in _amounts(text) if n not in source]
        if missing:
            problems.append(f"{where} '{text}': {', '.join(missing)} not in the source")
    return problems


def misread_numbers(verbatim: str, text_layer: str) -> list[str]:
    """Amounts in a transcription that the PDF's own text does not contain: a
    misread of the page picture, which no later step can catch."""
    exact = _stated(text_layer)
    return sorted({n for n in _amounts(verbatim) if n not in exact})


# ---- files ----------------------------------------------------------------------

def slugify(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    text = re.sub(r"['’]", "", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def existing_entry(book: Path, slug: str) -> Path | None:
    for base in ("recipes", "sections"):
        for folder in sorted((book / base).glob(f"*/{slug}")):
            return folder
    return None


# ---- the command ------------------------------------------------------------------

def main(root: config.BookRoot, paths: list[Path], *, page_spec: str = "", chapter: str = "",
         cook: str = "", title: str = "", model_name: str = models.DEFAULT_MODEL, dry_run: bool = False) -> int:
    cfg = config.load_or_exit(root)
    chapters = [c for c in cfg.chapters if c.kind == "recipes"]
    if not chapters:
        raise SystemExit("book.yaml has no recipe chapters (kind: recipes) to file recipes in")
    # A chapter by its folder name or its label, in any case: models answer with either.
    lookup = {key.casefold(): c for c in chapters for key in (c.name, c.label)}
    if chapter and chapter.casefold() not in lookup:
        raise SystemExit(f"--chapter {chapter!r} is not a recipe chapter: {', '.join(c.name for c in chapters)}")
    if not models.service():
        print(models.NO_KEY, file=sys.stderr)
        return by_hand(root, paths, page_spec=page_spec, chapter=lookup[chapter.casefold()] if chapter else None,
                       chapters=chapters, cook=cook, title=title, dry_run=dry_run)
    model = models.load(model_name)

    with tempfile.TemporaryDirectory() as t:
        pages = select(expand(paths, Path(t)), page_spec)
        page_of = dict(pages)
        print(f"Reading {len(pages)} page(s) with {model.name}…", flush=True)
        entries, unread = transcribe(model, pages)
        results: list[Result] = []
        for entry in entries:
            result = Result(entry, usage=entry.usage)
            results.append(result)
            if entry.kind != "recipe":
                continue
            try:
                fields, usage = model.json(normalize_prompt(entry.verbatim, chapters), NORMALIZE_SCHEMA)
            except models.Refused as exc:
                result.warnings = [f"not written: {exc}; transcribe it by hand"]
                continue
            result.usage = result.usage + usage
            result.judgment_calls = [c for c in fields["judgment_calls"] if c.strip()]
            result.warnings = unsupported_numbers(entry.verbatim, fields)
            if not any(i.strip() for g in fields["ingredient_groups"] for i in g["items"]):
                result.warnings.insert(0, "the ingredient list is empty: list what the text names")
            layer = "\n".join(page_of[n].text for n in entry.pages)
            if all(page_of[n].text for n in entry.pages):
                misread = misread_numbers(entry.verbatim, layer)
                if misread:
                    result.warnings.insert(0, f"transcription reads {', '.join(misread)}, "
                                              "which the PDF's own text does not contain")
            if not entry.complete:
                result.warnings.insert(0, f"looks incomplete: {entry.incomplete_reason}")
            home = lookup.get((chapter or fields["chapter"]).strip().casefold())
            if home is None:
                home = chapters[0]
                result.warnings.append(f"model chose no known chapter ({fields['chapter']!r}); filed in {home.name}")
            credited = cook or fields["cook"].strip()
            slug = slugify(fields["title"]) or slugify(entry.title)
            taken = existing_entry(root.book, slug)
            if taken:
                result.warnings.insert(0, f"not written: {taken.relative_to(root.path)} already exists")
                continue
            folder = root.book / "recipes" / home.name / slug
            result.folder = folder
            result.recipe_md = recipe_markdown(fields, home, credited, linked_source=True)
            if dry_run:
                continue
            kept = keep_pages(folder / "sources", [page_of[n] for n in entry.pages])
            labels = ", ".join(page_of[n].label for n in entry.pages)
            provenance = f"Transcribed by `cookbook ingest` ({model.name}, {_today()}) from {labels}."
            (folder / "sources" / "recipe-original.md").write_text(
                original_markdown(fields["title"].strip(), credited, entry.verbatim, provenance, kept), encoding="utf-8")
            (folder / "recipe.md").write_text(result.recipe_md, encoding="utf-8")
            models.log(root.book, {
                "command": "ingest",
                "entry": f"recipes/{home.name}/{slug}",
                "sources": labels,
                "model": model.name,
                **result.usage.record(),
                "checks": result.warnings,
                "notes": result.judgment_calls,
            })

    return report(root, results, dry_run, [page_of[n].label for n in unread])


# What a recipe added without AI holds until a person types it up: lint reports
# each TODO line as an error, so press cannot print it unfinished.
TYPE_INGREDIENTS = "TODO: type the ingredients from the original"
TYPE_DIRECTIONS = "TODO: type the directions from the original"


def by_hand(root: config.BookRoot, paths: list[Path], *, page_spec: str, chapter: config.Chapter | None,
            chapters: list[config.Chapter], cook: str, title: str, dry_run: bool) -> int:
    """Without AI: every page given is one recipe. Its pages are kept as the
    original, beside a recipe.md to type up in `cookbook studio` or an editor."""
    notes = []
    if not title.strip():
        title = re.sub(r"[-_\s]+", " ", paths[0].stem).strip().capitalize()
        notes.append(f"titled “{title}” from the file name: pass --title to choose")
    if chapter is None:
        chapter = chapters[0]
        notes.append(f"filed in {chapter.name}: pass --chapter to choose")
    slug = slugify(title)
    if not slug:
        raise SystemExit("give the recipe a title with --title")
    taken = existing_entry(root.book, slug)
    if taken:
        raise SystemExit(f"{taken.relative_to(root.path)} already exists: pass another --title")
    folder = root.book / "recipes" / chapter.name / slug
    where = folder.relative_to(root.path)
    fields = {"title": title.strip(), "ingredient_groups": [{"heading": "", "items": [TYPE_INGREDIENTS]}],
              "directions": [TYPE_DIRECTIONS], "notes": []}
    with tempfile.TemporaryDirectory() as t:
        pages = [page for _, page in select(expand(paths, Path(t)), page_spec)]
        if len(pages) > 2:
            notes.append(f"all {len(pages)} pages went into this one recipe: for a file holding several, "
                         "run once per recipe with --pages")
        if not dry_run:
            kept = keep_pages(folder / "sources", pages)
            provenance = (f"Added by `cookbook ingest` without AI ({_today()}) from "
                          f"{', '.join(p.label for p in pages)}.")
            (folder / "sources" / "recipe-original.md").write_text(
                original_markdown(fields["title"], cook, "", provenance, kept), encoding="utf-8")
            (folder / "recipe.md").write_text(recipe_markdown(fields, chapter, cook, linked_source=True),
                                              encoding="utf-8")
    print(f"\n{'WOULD WRITE' if dry_run else 'WROTE'}  {where}  ({len(pages)} page(s), to type up by hand)")
    for note in notes:
        print(f"  NOTE   {note}")
    if not dry_run:
        print(f"\nNext: type it up beside the original in cookbook studio (Recipes tab), or in {where}/recipe.md")
    return 0



def _money(usage: models.Usage) -> str:
    return "cost unknown" if usage.cost_usd is None else f"${usage.cost_usd:.4f}"


def report(root: config.BookRoot, results: list[Result], dry_run: bool, unread: list[str] = ()) -> int:
    from . import lint  # imports render, which needs the active root: only now

    written = [r for r in results if r.folder and r.recipe_md]
    status = 0
    for r in results:
        e = r.entry
        pages = f"p. {e.pages[0]}" if len(e.pages) == 1 else f"pp. {e.pages[0]}–{e.pages[-1]}"
        if e.kind != "recipe":
            print(f"\nSKIPPED  {e.title} ({pages}): not a recipe — add it as a page under book/sections/")
            continue
        where = r.folder.relative_to(root.path) if r.folder else "—"
        print(f"\n{'WOULD WRITE' if dry_run else 'WROTE'}  {where}  ({pages}, {_money(r.usage)})")
        for w in r.warnings:
            print(f"  CHECK  {w}")
        for c in r.judgment_calls:
            print(f"  NOTE   {c}")
        if dry_run and r.recipe_md:
            print("\n" + "\n".join(f"    {line}" for line in r.recipe_md.splitlines()))
        if not dry_run and r.folder:
            rep = lint.Report()
            lint.check_entry(rep, r.folder, "recipe.md", "recipe-original.md")
            lint.check_recipe_body(rep, r.folder, r.recipe_md)
            for line in rep.errors:
                print(f"  ERROR  {line}")
                status = 1
            for line in rep.warnings:
                print(f"  WARN   {line}")

    total = sum((r.usage for r in results), models.NO_USAGE)
    recipes = sum(r.entry.kind == "recipe" for r in results)
    print(f"\n{recipes} recipe(s), {len(results) - recipes} other entr{'y' if len(results) - recipes == 1 else 'ies'}; "
          f"{total.input_tokens:,} tokens in, {total.output_tokens:,} out, {_money(total)}")
    checks = sum(bool(r.warnings) for r in results)
    if checks:
        print(f"{checks} recipe(s) need a look against the original (CHECK lines above).")
    if unread:
        print(f"The model would not read {len(unread)} page(s): {', '.join(unread)}. "
              "Transcribe them by hand, or try another --model.")
        status = 1
    if written and not dry_run:
        slugs = ",".join(r.folder.name for r in written)
        print(f"Next: compare each with its original, then cookbook build --only {slugs}")
    return status
