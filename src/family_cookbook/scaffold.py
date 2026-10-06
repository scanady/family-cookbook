"""Scaffold a cookbook spec — book.yaml, the book/ tree, dividers, and matter —
and install the engine's agent files into a book root.

Creates only what is missing and never overwrites an existing file, so it is safe
to re-run when adding a chapter to a book that already has content.

Page content comes from the package's templates/ rather than being embedded
here, so the wording of a dedication or a divider can be edited without
touching code.

It writes book/book.yaml directly. That file carries the book's structure,
style, and curated layouts, so nothing in the engine needs editing.

Usage (from the new book's root):
    cookbook init --categories appetizers,soups-and-stews,desserts \\
        --sections household-tips \\
        --title "Our Family Cookbook" --subtitle "The Smith Family" [--dry-run]
"""
from __future__ import annotations

import re
import shutil
import sys
from importlib import resources
from pathlib import Path

TEMPLATES = resources.files(__package__) / "templates"
AGENT_FILES = resources.files(__package__) / "agent_files"

# The matter pages: each is its own single-page chapter, without a divider, at
# the ends of the book order. Always created, never passed in via --categories.
# The `matter-` prefix only groups them in a folder listing. The generated
# chapters (title page, contents, contributors, index) are declared by the
# book.yaml template and have no folder, so their names are reserved too.
MATTER_CHAPTERS = ("matter-dedication", "matter-closing-message")
RESERVED_CHAPTERS = (*MATTER_CHAPTERS, "title-page", "table-of-contents", "contributors", "index")

# Muted, print-safe accents to suggest. Screen-saturated colors print poorly on
# coated stock, so these stay low-chroma. Cycled when a category has no opinion.
SUGGESTED_ACCENTS = [
    "#7E3B3B", "#5A6B4E", "#8A6A3B", "#4E5F6B", "#6B4E5F",
    "#3F5A55", "#7A5C3E", "#55506B", "#6B5340", "#44605A",
]


def template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def slug_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", value))


def label_for(category: str) -> str:
    """Kebab-case category -> a reasonable display label ('and' becomes '&')."""
    words = [w.capitalize() if w != "and" else "&" for w in category.split("-")]
    return " ".join(words)


class Scaffolder:
    def __init__(self, root: Path, dry_run: bool) -> None:
        self.root = root
        self.dry_run = dry_run
        self.created: list[str] = []
        self.skipped: list[str] = []

    def write(self, path: Path, content: str) -> None:
        rel = path.relative_to(self.root).as_posix()
        if path.exists():
            self.skipped.append(rel)
            return
        self.created.append(rel)
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def mkdir(self, path: Path) -> None:
        rel = path.relative_to(self.root).as_posix() + "/"
        if path.is_dir():
            self.skipped.append(rel)
            return
        self.created.append(rel)
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)


def main(root: Path, categories: list[str], sections: list[str], title: str,
         subtitle: str, edition: str, dry_run: bool) -> int:
    bad = [c for c in categories + sections if not slug_ok(c)]
    if bad:
        print(f"error: names must be lowercase-kebab-case; bad: {', '.join(bad)}",
              file=sys.stderr)
        return 1
    if len(set(categories + sections)) != len(categories + sections):
        print("error: duplicate name across --categories and --sections", file=sys.stderr)
        return 1
    clash = set(categories + sections) & set(RESERVED_CHAPTERS)
    if clash:
        print(f"error: {', '.join(sorted(clash))} is created automatically; do not pass it in",
              file=sys.stderr)
        return 1

    book = root / "book"
    s = Scaffolder(root, dry_run)

    # Chapter folders only. Entries arrive via cookbook-recipe-ingest, and an
    # empty {slug}/ would be flagged by `cookbook lint`.
    for category in categories:
        s.mkdir(book / "recipes" / category)
    for section in sections:
        s.mkdir(book / "sections" / section)
    # A matter chapter IS one page: page.md at the chapter root, no {slug} level.
    s.write(book / "sections" / "matter-dedication" / "page.md", template("dedication.md"))
    s.write(book / "sections" / "matter-closing-message" / "page.md", template("closing-message.md"))

    # book/sections/{chapter}/page.md is the chapter's own page: the section
    # opener when entries follow, the whole chapter when they don't. Every
    # chapter gets a folder in the registry whether or not its entries live
    # elsewhere, so a chapter stays defined in one place. A prose chapter's
    # opener introduces pages, not recipes.
    for chapter in categories:
        s.write(book / "sections" / chapter / "page.md", template("chapter-page.md"))
    for chapter in sections:
        s.write(book / "sections" / chapter / "page.md", template("section-page.md"))

    chapter_block = "".join(
        f'  - name: {c}\n'
        f'    kind: {"prose" if c in sections else "recipes"}\n'
        f'    label: "{label_for(c)}"\n'
        f'    accent: "{SUGGESTED_ACCENTS[i % len(SUGGESTED_ACCENTS)]}"\n'
        for i, c in enumerate(categories + sections)
    )
    s.write(book / "book.yaml", template("book.yaml.tmpl").format(
        title=title, subtitle=subtitle, edition=edition, chapters=chapter_block,
    ))
    # No title-page file: the renderer generates that page from book.title,
    # book.subtitle, and book.edition. Authoring one would store the name twice.
    # Cover prose sits outside book/sections/ — those bases are paginated, and the
    # blurb would print twice: once on the cover, once as an interior page.
    s.write(book / "cover.md", template("cover.md"))
    # draft/ and the derived photo crops are build output, never source.
    s.write(root / ".gitignore", template("gitignore"))
    # Where the AI key goes, for ingest and photo; .gitignore keeps it out of history.
    s.write(root / ".env", template("env"))

    prefix = "would create" if dry_run else "created"
    print(f"{prefix}: {len(s.created)}")
    for path in s.created:
        print(f"  + {path}")
    if s.skipped:
        print(f"\nalready present, left alone: {len(s.skipped)}")
        for path in s.skipped:
            print(f"  = {path}")
    return 0


def install_agent_files(root: Path, update: bool) -> None:
    """Copy the engine's skills into .agents/skills/ and its content instructions
    into .github/instructions/. Without `update`, anything already present is left
    alone; with it, each engine skill folder and instruction file is replaced.
    .claude/skills and .github/skills link to .agents/skills so every agent
    finds the same copies. Where links are not allowed (Windows outside
    Developer Mode), they are copies instead, refreshed by `update`."""
    with resources.as_file(AGENT_FILES) as src:
        pairs = [(p, root / ".agents" / "skills" / p.name)
                 for p in sorted((src / "skills").iterdir()) if p.is_dir()]
        pairs += [(p, root / ".github" / "instructions" / p.name)
                  for p in sorted((src / "instructions").iterdir())]
        installed, kept = [], []
        for source, dest in pairs:
            rel = dest.relative_to(root).as_posix()
            if dest.exists() and not update:
                kept.append(rel)
                continue
            if dest.is_dir():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, dest)
            else:
                shutil.copyfile(source, dest)
            installed.append(rel)

    skills = root / ".agents" / "skills"
    for link in (root / ".claude" / "skills", root / ".github" / "skills"):
        rel = link.relative_to(root).as_posix()
        if link.is_symlink() or (link.exists() and not update):
            continue
        if not link.exists():
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                link.symlink_to(Path("..") / ".agents" / "skills", target_is_directory=True)
                installed.append(f"{rel} -> ../.agents/skills")
                continue
            except OSError:
                pass
        # A copy, merged into any folder already there, so skills of the
        # family's own beside it survive an update.
        shutil.copytree(skills, link, dirs_exist_ok=True)
        installed.append(f"{rel} (a copy of .agents/skills)")

    print(f"agent files installed: {len(installed)}")
    for rel in installed:
        print(f"  + {rel}")
    if kept:
        print(f"already present, left alone (cookbook agent-files --update replaces them): {len(kept)}")
        for rel in kept:
            print(f"  = {rel}")
