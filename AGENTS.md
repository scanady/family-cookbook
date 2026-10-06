# family-cookbook engine — Agent Guide

<!-- shared-principles:start -->
## Read the general principles first

They are authored once, in [.github/instructions/](.github/instructions/), and are not repeated here:

| File | Owns |
|---|---|
| [core-principles](.github/instructions/core-principles.instructions.md) | Think before acting; build for people; coherence. |
| [coding-principles](.github/instructions/coding-principles.instructions.md) | Simplicity, scope, completion, modernization, DRY. |

**Read `coding-principles` before your first edit.** This file adds only what is specific to this repository.
<!-- shared-principles:end -->

## What this repository is

The engine that turns a *book root* — `book/book.yaml` plus markdown recipes and
pages — into a screen draft and press-ready PDFs. It is installed into each
book's repository as the `family-cookbook` package and driven by one CLI,
`cookbook`. No book's content lives here except the public examples in
`examples/`.

Keep the engine free of any one family: no names, recipe titles, slugs, or
page counts of a real book in code, comments, docs, or agent files. Calibration
notes describe the method, not the book it was measured on.

## Layout

- `src/family_cookbook/cli.py` — the `cookbook` command. Resolves the book root
  from `--book` (default: the current directory or the nearest folder above it
  holding `book/book.yaml`), activates it with `config.activate()`, then imports
  the modules that lay the book out — they read the active root at import time.
- `config.py` — `BookRoot`, `find_root()`, and the `book.yaml` loader.
- `render.py` — book order, archetype assignment, every page renderer, print
  CSS, FIT_SCRIPT, the generated pages. `main()` writes the draft or print HTML.
- `cover.py` — the casewrap cover. `lulu.py` — Lulu's page-count tables (spine
  width, recommended gutter, hardcover minimum).
- `lint.py`, `fit_images.py`, `check.py`, `index.py`, `export.py` — the other
  commands. `scaffold.py` — `cookbook init` and `cookbook agent-files`.
  `doctor.py` — `cookbook doctor`, the setup checks with the fix for each.
- `audit.py` — `cookbook audit`: the content checks (truncation, cook time,
  invented figures, missing ingredients, dropped lines, same cook, personal
  data) and the book report, which also gathers lint, the photo rules, and
  `check`. Deterministic and offline; `cookbook review` shows its findings per
  entry. A new check needs a seeded-defect test in `tests/test_audit.py` and a
  run on a real book: tune it until the remaining findings are real.
- `ingest.py`, `photo.py`, `review.py` — the AI intake commands: transcribe
  cards, generate dish photos, review against the originals. `models.py` puts
  the AI services behind one interface (`GEMINI_API_KEY` for Google's API,
  else `OPENROUTER_API_KEY` for the same models through OpenRouter, from the
  book's `.env`) and logs cost to `book/sources/ai-log.jsonl`. With no key, `ingest`
  and `photo` print `models.NO_KEY` and carry on without AI; nothing else needs
  a key. Their prompts load the rules from the agent files, so a rule changes
  in one place. Tests use stand-in models; never call a real model from `tests/`.
- `studio.py` — `cookbook studio`, the local web app for working on an existing
  book without a terminal: draft, review (review.py's own editor and endpoints),
  chapter and entry order, keepsakes, report, and the print files. It
  edits `book.yaml` as text so comments survive, and keeps a write only if it
  re-parses to exactly the change. Builds, the report, and the press run in a
  fresh process each, since the layout modules read `book.yaml` on import.
- `press.py` — the press sequence, shared by `cookbook press` and the studio.
- `fonts/` (OFL), `templates/` (what `cookbook init` writes), `agent_files/`
  (skills and content instructions copied into book roots) are package data.
- `docs/` — user documentation: `COMMANDS.md` (every command, the book's
  folder, installing by hand, upgrading, the container, the example book),
  `TROUBLESHOOTING.md` (problems and the glossary), `PRINTING.md` (the print
  specification and press workflow for any book), `RECIPE-FORMAT.md` (recipe,
  page, photo, and keepsake files), `BOOK-YAML.md` (every `book.yaml` key),
  `LAYOUTS.md` (the archetypes and how they are assigned; its images, in
  `docs/images/`, are screenshots of the example book's draft). A change to a
  format, key, command, or layout rule updates the doc that describes it, and
  `docs/COMMANDS.md`'s command tables.
- `README.md` (start here for users: install and the five commands most books
  need; keep it that short), `CONTRIBUTING.md` (issues only, no pull requests).
- `install.ps1` (Windows, the default the README shows first) and `install.sh`
  (macOS, Linux) — the one-step setup and upgrade for a book folder: Python if
  missing (Windows), venv, engine from the release's source archive, Chromium,
  Ghostscript (Windows), `cookbook init`, the key, a `./cookbook` launcher,
  `cookbook doctor`. Their `VERSION` is the release tag they install; CI runs
  both against the checkout, `install.ps1` under Windows PowerShell 5.1.
- Windows: Ghostscript is `gswin64c`, found off PATH under Program Files
  (`export.find_ghostscript`); console and subprocess text is UTF-8 explicitly;
  skill links fall back to copies.
- `examples/{book}/` — complete public book roots; CI builds each in print mode.

The engine makes the book's files to the printer's specification and stops
there: ordering, payment, and anything beyond the two PDFs are out of scope.

Page geometry, fonts, and archetype rotations are engine code, not per-book
config: they satisfy the vendor spec in `docs/PRINTING.md` and are checked by
`cookbook check`. Everything a book decides lives in its `book.yaml`.

Agent files in `src/family_cookbook/agent_files/` ship to book repositories, where
the engine source is not present: they reference `cookbook ...` commands and
"the engine's `render.py`", and link this repository's `docs/PRINTING.md` by URL.

## Build and validation

- `python -m pytest` — tests of real boundaries: Lulu's tables, book-root
  discovery, `cookbook init`'s placeholders, layout assignment, the audit's
  checks (seeded defects), ingest, photo, review, and the studio against stand-in
  models, and the example book's four seeded review defects.
- Rendering changes: build an example and look at it.
  `cookbook build --book examples/<book> --only slug` for one entry;
  `cookbook build --print --book examples/<book>` then `cookbook check --book examples/<book>`
  for the press path. Source review alone is insufficient — the parser and
  layout engine can drop or clip content that looks valid in markdown.
- A change that must not alter output: build a real book before and after and
  diff `draft/cookbook-print.html`.
- `.github/workflows/ci.yml` lints, fits, builds, checks, and covers every book in
  `examples/`, and runs `cookbook init` on a fresh two-recipe book through
  `cookbook press`.

## Releases

Bump `version` in `pyproject.toml`, `__version__` in
`src/family_cookbook/__init__.py`, and `VERSION` in `install.sh` and
`install.ps1`; update the tag in `docs/COMMANDS.md`'s install-by-hand steps; add
a `CHANGELOG.md` entry; and tag `vX.Y.Z`. Book repositories pin the tag.

## Repository hygiene

Delete one-off migration, debugging, and probe scripts after use, together with
their temporary outputs. Keep a new script only when it becomes a supported
`cookbook` command, and document it in `docs/COMMANDS.md`.
