---
name: cookbook-init
description: 'Initialize a new cookbook spec — scaffold the book/ tree, layout manifest, front and back matter, and section dividers with `cookbook init` — so a new book repository becomes a family''s cookbook. Also used to add a new section to an existing book. Use when asked to "start a new cookbook", "initialize the book spec", "set up my own family cookbook", "scaffold a cookbook", or "add a new section to the book".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: cookbook-recipe-ingest, cookbook-lint
---

# Cookbook Spec Initialization

Stand up a new `book/` spec — either a whole cookbook in a new book repository, or a new section in an existing one.

## Role Definition

You are setting up the structure someone else will fill with their family's recipes. The structure is the part that is hard to change later: once fifty entries exist, renaming a category means touching the manifest, the dividers, and every path. Get the categories and their order right at the start, and confirm them with the user rather than assuming this book looks like any other.

## When To Use

Use this for a fresh cookbook in a new book repository, or to add a new category section to a book that already exists.

Do not use it to add a single recipe (`cookbook-recipe-ingest`) or to check an existing book (`cookbook-lint`).

## What A Cookbook Spec Is

Everything the book is made of lives under `book/`, in three bases chosen by **role**:

```
book/
  book.yaml                       structure, style, and curated layout assignments

  recipes/{chapter}/{slug}/       RECIPE CHAPTERS — food only
    recipe.md                     the clean entry
    sources/recipe-original.md    verbatim transcription
    images/{slug}.jpg             canonical photo
    prompts/                      image prompt (and an optional layout note)

  sections/{chapter}/page.md      the chapter's own page: divider message, or the whole page
  sections/{chapter}/{slug}/      PROSE CHAPTERS — family notes, tips, jokes
    page.md
    sources/page-original.md
  sections/matter-{name}/page.md  one-page chapters (divider: false) — dedication, closing message

  cover.md                        back-cover copy
  sources/                        whole-book source material (an original scanned edition)
```

The distinction that matters: **`recipes/` and `sections/` are both chapters.** Each takes a place in the `chapters:` list in `book/book.yaml`, a section divider, a display label, and an accent color. They differ only in entry format — `recipe.md` with Ingredients and Directions, versus `page.md` prose. Front and back matter are chapters too (`matter-dedication`, `matter-closing-message`), each a single page with `divider: false`, positioned in the same list.

Which base a chapter lives in is discovered from the tree, so creating `book/sections/kitchen-notes/` is enough to make a prose chapter exist.

`book/book.yaml` declares all of it — chapter order, display labels, accent colors, per-chapter entry pinning, the book's identity, cover settings, and curated layouts. A chapter folder with no block there still renders, at the end of the book in the default color, and `cookbook lint` warns about it.

Page geometry (trim, bleed, margins, gutter), the fonts, and the archetype rotations stay in the engine's `render.py` on purpose. Those satisfy the vendor spec in [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) and are gated by `cookbook check` — they are not per-book settings, and a config file would make them look editable.

A chapter name must not appear in both `recipes/` and `sections/`. The renderer resolves one and drops the other silently; the linter treats it as an error.

## Workflow

### Step 1: Establish the book's identity

Ask, and do not guess:

- **Title, subtitle, edition.** Who the book is by and for.
- **Recipe chapters, in the order they should appear.** The default set is a reasonable starting point, but a book with no drinks section should not ship an empty drinks divider.
- **Prose chapters, if any.** A section for household tips, family lore, or jokes. Optional — many books have none.
- **Whether an original edition exists** — a scanned prior cookbook being reissued, which belongs in `book/sources/`.

Offer the default chapter list as a starting point and let the user cut and add. Do not carry over another book's family names, dedication, or accent colors as if they were defaults.

### Step 2: Scaffold

From the new book's root (the repository that will hold `book/`):

```bash
cookbook init \
  --categories appetizers,soups-and-stews,meat,sides,desserts \
  --sections other-family-secrets \
  --title "Our Family Cookbook" --subtitle "The Smith Family"
```

`--categories` creates recipe chapters under `book/recipes/`; `--sections` creates prose chapters under `book/sections/`. Both get a divider message at `book/sections/{chapter}/page.md`. The `matter-dedication` and `matter-closing-message` chapters are always created and are not passed in. `--edition` sets the edition line; `--book PATH` targets a directory other than the current one.

Run with `--dry-run` first to see what it would create. `cookbook init` refuses to overwrite existing files, so it is safe to re-run when adding a chapter: pass the full list and it creates only what is missing. It rejects names that are not lowercase kebab-case, a name used in both lists, or a matter chapter name passed in.

It writes the chapter folders, `book/book.yaml` with every chapter already declared, a divider message per chapter, dedication and closing-message stubs, and a `book/cover.md` back-cover stub. It also writes a `.gitignore` and installs the agent files (these skills under `.agents/skills/`, the content instructions under `.github/instructions/`; refresh them later with `cookbook agent-files --update`). It writes no title page, contents, contributors, or index: those are `kind: generated` chapters in `book.yaml`, built by the renderer from the config and every entry's title and attribution, placed by their position in `chapters:`. The index block is written commented out — it is optional; uncomment it to print an A–Z index of dishes and cooks. Never author them. Nothing in the engine needs editing — the config is the wiring.

The page wording comes from the templates shipped in the engine package (`family_cookbook/templates/`), not from this skill. To change what every new book's dedication or dividers say, edit those templates in the engine; for one book, just edit the scaffolded pages. A missing template fails the run loudly, including under `--dry-run`.

### Step 3: Review book.yaml

`cookbook init` already wrote it — there is nothing to wire into the engine. Read it through and fix what it could only guess at:

- **Chapter order.** The `chapters:` list order *is* the book's order.
- **Labels.** The scaffold derives them mechanically from the folder name; `Breads Pancakes And French Toast` wants to become `Breads, Pancakes & French Toast`.
- **Accents.** These are cycled from a generic palette. They tint each chapter's rules and headings, so pick them deliberately: muted, print-safe tones that differ between adjacent chapters. A saturated screen color prints badly on coated stock.
- **Cover.** `spine_text` and `photo` are placeholders. The back-cover blurb and sign-off are prose in `book/cover.md`, not `book.yaml` — `back_blurb`/`back_signoff` keys there are a lint error.

A malformed `book.yaml` stops every `cookbook` command with a readable message rather than a traceback, so run `cookbook build` after editing to confirm it still loads.

### Step 4: Write the front and back matter

The scaffold leaves stubs. Replace them — the dedication, the closing message, and the back-cover copy in `book/cover.md` are the most personal pages in the book, and placeholder text in them is worse than their absence.

Their order is their position in the `chapters:` list in `book/book.yaml`. Within a multi-entry chapter, a `pinned` list holds named slugs at the front; the rest follow alphabetically.

### Step 5: Write the section dividers

Each divider prints the chapter's `label` from `book.yaml` as its heading, then one line of family voice from `book/sections/{chapter}/page.md` — the scaffold writes a placeholder line. These are the seams of the book; generic filler shows. Write them, or delete the file (the chapter still opens with its name, just without a message).

### Step 6: Verify the empty book builds

```bash
cookbook lint
cookbook build
```

A book with dividers and front matter and no recipes should still render. Confirm the sections appear in the intended order with the intended colors before any content goes in — reordering is cheap now and expensive later.

Then ingest the first recipe with `cookbook-recipe-ingest` and rebuild.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Scaffold command | `cookbook init` | Creating the tree and book.yaml (Step 2) |
| Page templates | The engine's `family_cookbook/templates/` | Changing what every new book's dedication, closing message, or dividers say (Steps 2, 4–5) |
| Book configuration | `book/book.yaml` | Chapter order, labels, accents, entry pinning, cover settings (Steps 3–4) |
| Config loader | The engine's `config.py` | Understanding what the config accepts and how it fails |
| Divider and matter conventions | `.github/instructions/book-pages.instructions.md` | Writing the front matter, back matter, and dividers (Steps 4–5) |
| Entry format | `.github/instructions/recipe-content.instructions.md` | Explaining what entries will look like once content arrives |
| Print specification | [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) | The new book targets a different trim size or vendor |
| First recipe | `cookbook-recipe-ingest` | The structure is verified and content is ready to go in (Step 6) |

## Constraints

### MUST DO

- Ask for title, subtitle, and the chapter list — recipe and prose both — in book order; do not infer them from another book.
- Run `cookbook init` with `--dry-run` first and show the user what it would create.
- Review every generated `book.yaml` value — the scaffold guesses labels and cycles accents; both usually need a human.
- Choose muted, print-safe accents that differ between adjacent sections.
- Replace every TODO placeholder — in the dedication, closing message, dividers, `book/cover.md`, and `book.yaml` (the subtitle) — `cookbook lint` reports each as an error, and `cookbook press` will not build until none remain.
- Verify the empty book builds and the sections appear in the intended order before content goes in.

### MUST NOT DO

- Carry over another book's family name, dedication, attributions, or accent colors as defaults.
- Overwrite existing content — the scaffold refuses to, and neither should you.
- Create a chapter folder with no block in `book.yaml`; it renders at the end of the book in the default color.
- Give the same name to a folder in both `book/recipes/` and `book/sections/` — one of them is dropped silently.
- Put prose under `book/recipes/`; that base holds food only.
- Leave placeholder text in the most personal pages of the book.
- Ship a divider for a section that will have no entries — no file means no divider.
- Create empty entry folders as placeholders; `cookbook lint` flags them.

## Knowledge Reference

Cookbook spec scaffolding, book tree skeleton, recipe chapters, prose chapters, structural furniture, three-base book layout, layout manifest header, section divider stub, front matter, back matter, dedication page, title page, book structure order, category display labels, print-safe section accents, category slug validation, idempotent scaffold, cookbook init, engine page templates

## Done When

- `book/` exists with every requested category, a divider each, and front/back matter.
- `book/book.yaml` declares every chapter in the intended order, with reviewed labels and accents.
- No placeholder text remains in the dedication, closing message, dividers, cover copy, or `book.yaml`.
- `cookbook lint` is clean and `cookbook build` renders the sections in the intended order.
