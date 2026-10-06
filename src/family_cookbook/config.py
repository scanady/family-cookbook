"""Find the book root and load book/book.yaml — the cookbook's structure, style, and layout.

Adding a chapter is one block in book.yaml plus the folder; nothing in the
engine needs editing.

What deliberately stays in code: page geometry (trim, bleed, margins, gutter)
and the font faces. Those are vendor constraints verified against the spec table
in docs/PRINTING.md and gated by `cookbook check` — not per-book settings, and
making them look editable in a config file would invite breaking print
correctness. Archetype rotations stay in render.py for the same reason: they
tune the renderer, they don't describe a book.

Consumed by render.py, cover.py, and lint.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BookRoot:
    """A book repository: book/ holds the spec, draft/ the generated output."""
    path: Path

    @property
    def book(self) -> Path:
        return self.path / "book"

    @property
    def draft(self) -> Path:
        return self.path / "draft"

    @property
    def config_path(self) -> Path:
        return self.book / "book.yaml"

    @property
    def cover_copy_path(self) -> Path:
        return self.book / "cover.md"


def find_root(start: Path) -> BookRoot:
    """The nearest folder at or above `start` that holds book/book.yaml."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / "book" / "book.yaml").is_file():
            return BookRoot(folder)
    raise ConfigError(
        f"no book/book.yaml in {start} or any folder above it — "
        "run from a book root, pass --book PATH, or start one with `cookbook init`"
    )


# The book the command operates on. The CLI resolves it from --book and
# activates it before importing the modules that lay the book out, which read
# it at import time.
_active: BookRoot | None = None


def activate(root: BookRoot) -> None:
    global _active
    _active = root


def active_root() -> BookRoot:
    if _active is None:
        raise RuntimeError("no book root is active — the cookbook CLI activates one from --book")
    return _active


def load_env(root: BookRoot) -> None:
    """Credentials from `<book root>/.env` (KEY=VALUE lines, # comments) into the
    environment, never overriding a variable already set. The file holds the AI
    model key (GEMINI_API_KEY); the book's .gitignore keeps it out of history."""
    import os

    path = root.path / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.split(" #")[0].strip().strip("\"'")
        os.environ.setdefault(key.strip(), value)


# The top-level keys load() reads. Anything else in book.yaml is ignored, which
# `cookbook lint` reports, so a leftover or misspelled block is not silent.
TOP_LEVEL_KEYS = ("book", "style", "cover", "audit", "chapters", "layouts")

# A chapter's `kind` picks which base its entries live under.
KIND_BASE = {"recipes": "recipes", "prose": "sections"}

# `kind: generated` chapters are pages the renderer builds from config and the
# finished page order, so they have no folder and must never be authored. Each
# maps to what its words come from; the chapter's position in the list is where
# it prints, and its `label` is its heading.
GENERATED_PAGES = {
    "title-page": "book.title / book.subtitle / book.edition",
    "table-of-contents": "the book's own page order",
    "contributors": "the attribution line of every entry",
    "index": "every entry's title and attribution",
}
KINDS = (*KIND_BASE, "generated")

# A layouts row's optional `extras:` value: print the entry's keepsakes inset on
# its own page, or on a keepsake page of their own right after it.
EXTRAS_PLACEMENTS = ("inset", "page")

# Front and back matter are chapters too. A dedication is a chapter without a
# divider placed before the first food chapter; a closing message is one placed
# after the last. Everything that used to make them special — position, no
# divider, their own entry order — is now said in the chapters list itself, so
# there is no second kind of section for the code to know about.


class ConfigError(Exception):
    """book.yaml is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class Chapter:
    name: str
    kind: str
    label: str
    accent: str
    divider: bool = True   # chapters open with a divider unless told otherwise
    toc: bool = True       # ...and are listed in the table of contents
    pinned: tuple[str, ...] = ()  # entry slugs held at the front; rest follow alphabetically

    @property
    def generated(self) -> bool:
        """Built by the renderer (title page, contents, contributors, index)."""
        return self.kind == "generated"

    @property
    def base(self) -> str:
        """Which of book/{recipes,sections}/ holds this chapter's entries.

        Empty for a generated chapter: it has no folder anywhere in book/."""
        return KIND_BASE.get(self.kind, "")

    @property
    def entry_filename(self) -> str:
        return "recipe.md" if self.kind == "recipes" else "page.md"


@dataclass
class BookConfig:
    title: str
    subtitle: str
    edition: str
    default_accent: str
    cover: dict
    chapters: list[Chapter]
    book_dir: Path
    layouts: list[dict] = field(default_factory=list)
    # `audit: estimates: true` — a Yield or Prep time written "About …" is the
    # family's own estimate, which `cookbook audit` accepts though no source states it.
    estimates: bool = False

    # -- derived views, so callers don't each re-walk the chapter list ---------

    @property
    def by_name(self) -> dict[str, Chapter]:
        return {c.name: c for c in self.chapters}

    @property
    def book_structure(self) -> list[str]:
        """Every chapter, in book order. The list is the order."""
        return [c.name for c in self.chapters]

    @property
    def toc_categories(self) -> list[str]:
        """Chapters listed in the table of contents."""
        return [c.name for c in self.chapters if c.toc]

    @property
    def divider_categories(self) -> list[str]:
        """Chapters open with a divider; front and back matter do not.

        Whether a chapter has one is configuration, not a file's existence. The
        divider's *message* is content and lives in
        book/sections/{name}/page.md, with the rest of that section's own
        material. Optional: a divider showing only its name is a fine opener.
        """
        return [c.name for c in self.chapters if c.divider]

    @property
    def labels(self) -> dict[str, str]:
        return {c.name: c.label for c in self.chapters}

    @property
    def accents(self) -> dict[str, str]:
        return {c.name: c.accent for c in self.chapters}

    @property
    def pinned_entries(self) -> dict[str, list[str]]:
        """Per-chapter pinned slugs; anything unpinned follows alphabetically.

        `pinned` holds entries at the FRONT of their chapter. It cannot hold one
        at the back — that is why it is not called `order`.
        """
        return {c.name: list(c.pinned) for c in self.chapters if c.pinned}

    def base_for(self, category: str) -> str:
        """Which base a category's entries live under.

        Configured chapters answer from `kind`. An unconfigured folder still
        resolves — render.py renders it at the end of the book rather than
        dropping it — so the filesystem is the fallback, not the source.
        """
        chapter = self.by_name.get(category)
        if chapter:
            return chapter.base
        if (self.book_dir / "sections" / category).is_dir():
            return "sections"
        return "recipes"


def load_cover_copy(root: BookRoot) -> tuple[str, str]:
    """Read the back-cover prose from book/cover.md -> (blurb, signoff).

    Cover copy is prose someone wrote, so it lives in markdown rather than in
    book.yaml alongside colors and file paths. It cannot live under book/sections/
    either: those bases are paginated, and the blurb would print twice — once on
    the cover and once as an interior page.

    Shape is the same convention a section divider uses: an H1 that names the
    file, body paragraphs, and a trailing *italic* line. Paragraphs become the
    blurb; the italic line becomes the sign-off. Both are optional.
    """
    path = root.cover_copy_path
    if not path.exists():
        return "", ""

    paragraphs, signoff = [], ""
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        block = " ".join(block.split())
        if not block or block.startswith("#"):
            continue
        if block.startswith("*") and block.endswith("*") and not block.startswith("**"):
            signoff = block[1:-1].strip()
        else:
            paragraphs.append(block)
    return " ".join(paragraphs), signoff


def load_or_exit(root: BookRoot) -> BookConfig:
    """load(), but a bad config exits with a readable message, not a traceback.

    Every caller is a command-line tool, and a stack trace through the YAML
    parser tells the person editing book.yaml nothing they can act on.
    """
    try:
        return load(root)
    except ConfigError as exc:
        import sys as _sys
        print(f"error: {exc}", file=_sys.stderr)
        raise SystemExit(2) from None


def _require(mapping: dict, key: str, where: str) -> object:
    if key not in mapping:
        raise ConfigError(f"{where}: missing required key {key!r}")
    return mapping[key]


def load(root: BookRoot) -> BookConfig:
    path = root.config_path
    if not path.exists():
        raise ConfigError(f"{path} not found — the book has no configuration")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a mapping at the top level")

    book = raw.get("book") or {}
    style = raw.get("style") or {}
    default_accent = style.get("default_accent", "#3F3A34")

    chapters: list[Chapter] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw.get("chapters") or []):
        where = f"{path.name}: chapters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: each chapter must be a mapping")
        name = str(_require(entry, "name", where))
        kind = str(entry.get("kind", "recipes"))
        if "order" in entry:
            raise ConfigError(
                f"{where}: `order` was renamed to `pinned`, because it holds entries at "
                "the FRONT of a chapter and cannot pin one last. Rename the key"
            )
        if kind not in KINDS:
            raise ConfigError(
                f"{where}: kind {kind!r} is not one of {', '.join(sorted(KINDS))}"
            )
        generated = kind == "generated"
        if generated:
            if name not in GENERATED_PAGES:
                raise ConfigError(
                    f"{where}: {name!r} is not a page the renderer can generate; "
                    f"generated chapters are {', '.join(GENERATED_PAGES)}"
                )
            # A generated page has no folder, so nothing to open or pin.
            for key in ("divider", "pinned"):
                if entry.get(key):
                    raise ConfigError(f"{where}: a generated chapter takes no `{key}`")
        elif name in GENERATED_PAGES:
            raise ConfigError(
                f"{where}: {name!r} is a generated page — declare it `kind: generated`"
            )
        if name in seen:
            raise ConfigError(f"{where}: duplicate chapter {name!r}")
        seen.add(name)
        chapters.append(Chapter(
            name=name,
            kind=kind,
            label=str(entry.get("label") or name.replace("-", " ").title()),
            accent=str(entry.get("accent") or default_accent),
            divider=bool(entry.get("divider", not generated)),
            toc=bool(entry.get("toc", True)),
            pinned=tuple(str(s) for s in (entry.get("pinned") or [])),
        ))

    layouts = []
    for i, entry in enumerate(raw.get("layouts") or []):
        where = f"{path.name}: layouts[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: each layout must be a mapping")
        for key in ("chapter", "slug", "archetype"):
            _require(entry, key, where)
        # Optional: where the entry's extras/ keepsakes print, overriding the
        # renderer's room estimate. Absent means "inset if the page has room".
        if "extras" in entry and entry["extras"] not in EXTRAS_PLACEMENTS:
            raise ConfigError(
                f"{where}: extras {entry['extras']!r} is not one of "
                f"{', '.join(EXTRAS_PLACEMENTS)}"
            )
        layouts.append(entry)

    audit = raw.get("audit") or {}
    if not isinstance(audit, dict) or not isinstance(audit.get("estimates", False), bool):
        raise ConfigError(f"{path.name}: audit must be a mapping, and audit.estimates true or false")

    return BookConfig(
        title=str(book.get("title", "Family Cookbook")),
        subtitle=str(book.get("subtitle", "")),
        edition=str(book.get("edition", "")),
        default_accent=default_accent,
        cover=raw.get("cover") or {},
        chapters=chapters,
        book_dir=root.book,
        layouts=layouts,
        estimates=audit.get("estimates", False),
    )
