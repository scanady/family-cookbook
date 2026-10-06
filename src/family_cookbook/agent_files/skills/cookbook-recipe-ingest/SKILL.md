---
name: cookbook-recipe-ingest
description: 'Add a new recipe or non-recipe page to the family cookbook from a photographed card, a scan, pasted text, or an emailed family note — transcribing it verbatim, normalizing it into the book''s entry format, filing it in the right category, and verifying it renders. Use when asked to "add this recipe", "ingest this recipe card", "put Ruth''s recipe in the cookbook", "transcribe this recipe", or "add a page to the cookbook".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: cookbook-lint, cookbook-recipe-remove, design-visual-cookbook-image-generator
---

# Cookbook Recipe Ingestion

Take a recipe in whatever form it arrived — a phone photo of an index card, a scanned page, a forwarded email, text pasted into chat — and file it into `book/` as a proper entry that renders in the book.

## Role Definition

You are an archivist transcribing family documents, not a recipe writer. Your job is fidelity first and format second. The handwriting quirks, the missing oven temperature, the ingredient listed with no amount, the aside about who this dish reminds someone of — these are the reason the book exists. You preserve them. You normalize *structure*, never *substance*.

## When To Use

Use this to add any new entry to the book: a food recipe, or a non-recipe page (family note, household tip, joke, poem).

Do not use it to generate the dish photograph (`design-visual-cookbook-image-generator`), to assign a page layout (`design-visual-cookbook-page-layout` — most entries are auto-assigned and need nothing), or to remove an entry (`cookbook-recipe-remove`).

## The Cardinal Rule

**Never invent.** If the card does not say how long to bake it, the recipe does not say how long to bake it. Write `Not specified`, or omit the field. Do not infer a temperature from similar recipes, do not add a step the cook obviously performed, do not convert "a good handful" into "1/2 cup".

Fixing a clear OCR or transcription artifact — `1 lb. hambwrger` → `1 lb. hamburger` — is correct. Rewriting `Mix it all up good` into `Combine thoroughly` is not. The family voice is content.

When something is genuinely illegible, transcribe what you can and mark the gap: `2 [illegible] flour`. Then tell the user which entries have gaps so a human can check the original.

## Photos, scans, and PDFs: run `cookbook ingest` first

When the recipe arrived as an image or a PDF, let the command do Steps 1–3 and the first pass of Step 4:

```bash
cookbook ingest card-front.jpg card-back.jpg      # the pages of one source, in order
cookbook ingest family-cookbook.pdf --pages 12-30 # a range of a longer document
cookbook ingest card.jpg --cook "Ruth Baker"      # credit a card that names no one
```

It uses AI when the book's `.env` has `GEMINI_API_KEY` or `OPENROUTER_API_KEY`. It reads the pages with a vision model, joins recipes that run across pages, files each recipe in a chapter from `book/book.yaml`, and writes `recipe.md`, `sources/recipe-original.md`, and the page images under `sources/`. Prose entries are reported as `SKIPPED`, not written: ingest those by hand.

Without a key it prints `AI is off` and files all the pages given as one recipe (`--title`, `--chapter`), with the page images under `sources/` and a `recipe.md` whose ingredients and directions are `TODO` lines. The folder settles Step 2; continue the manual workflow below at Step 3, keeping the page images, and replace every `TODO` line.

Its output is a first draft for you to verify, not a finished entry. Then:

- Read every `CHECK` line and settle it against the page image in `sources/`: an incomplete recipe, an amount the source does not state, a number the PDF's own text contradicts, a slug that already exists.
- Read every `NOTE` line: each is an interpretation the model made. Undo any that breaks the Cardinal Rule below.
- Have the person who knows the family check each recipe against its card with `cookbook review` (page images, transcription, and `recipe.md` side by side; edit, then approve), then continue at Step 6. Without a person, compare each `recipe.md` with its `sources/recipe-original.md` yourself.

Use the manual workflow below for text that is not an image or PDF (pasted, emailed, dictated), and for any entry the command got wrong.

## Workflow

### Step 1: Read the source and decide what it is

Three destinations, by role:

- A **food recipe** goes under `book/recipes/{category}/{slug}/recipe.md`.
- A **prose chapter entry** — a note about removing stains, a joke about dieting, a poem, a household tip — goes under `book/sections/{category}/{slug}/page.md`.
- **Front or back matter** — a dedication, a closing message — is a one-page chapter: `book/sections/matter-{name}/page.md` (e.g. `matter-dedication`), with `divider: false` and its place in the `chapters:` list of `book/book.yaml`.

The split is absolute: `book/recipes/` contains only things you cook, and everything else is prose under `book/sections/`. Front and back matter are chapters like any other; what makes them open and close the book is `divider: false` and their position in `chapters:`, not the folder.

If the source holds several recipes (a scanned page with two on it), treat each as a separate entry and ingest them one at a time.

### Step 2: Choose category and slug

Pick the chapter from the ones already in the book. The `chapters:` list in `book/book.yaml` is the authoritative list and its order.

Adding a *new* chapter is a book-structure change, not an ingestion: it needs a block in `chapters:` (name, kind, label, accent) plus the folder. Do not do it silently — say what the new chapter needs and confirm before adding one.

The slug is lowercase kebab-case derived from the title, with possessives and punctuation flattened: `Ruth's Apple Cake` → `ruths-apple-cake`, `Chicken, Peas & Dumplings` → `chicken-peas-and-dumplings`. Check the category folder for a near-duplicate slug before creating one — a book may well hold both `beef-stew` and `noras-beef-stew`, and that is deliberate: two contributors, two different recipes, so the second takes the contributor's name to keep them apart.

### Step 3: Write the verbatim transcription first

Before normalizing anything, write the source exactly as it reads to:

- `book/recipes/{category}/{slug}/sources/recipe-original.md`, or
- `book/sections/{category}/{slug}/sources/page-original.md`, or
- `book/sections/matter-{name}/sources/page-original.md`

Preserve line breaks, capitalization, abbreviations, ordering, and marginalia. This file is the archive; the clean file is derived from it. If the source is a photograph, the transcription is your reading of it — and it is what a future reader will compare against the original card.

Skip this file only when there is no original document at all (a recipe dictated over the phone, something composed for the book directly). Never write a transcription that is really just a copy of your cleaned-up version.

### Step 4: Write the clean entry

Follow the entry format in `.github/instructions/recipe-content.instructions.md` for recipes and `.github/instructions/book-pages.instructions.md` for pages. Those files are the specification — read them rather than working from memory, and do not restate their rules here.

The points most often gotten wrong:

- **Attribution goes on its own line** as `*Name*` under the title. Every entry that came from a person should credit them.
- **`## Ingredients` and `## Directions` are mandatory in a recipe**, even when the source is a flowing paragraph with no lists. Split it.
- **Directions are one sequentially numbered list.** No bold phase headings inside it — fold `For the sauce:` into the step text. Bold subheads are allowed only inside Ingredients, for sub-recipes.
- **Stories and serving suggestions go in `## Notes`**, not into a direction step.
- **Only link `sources/recipe-original.md` if you wrote one.**

### Step 5: Photograph, if one is wanted

A recipe with no photo renders fine — the layout engine assigns it a text archetype. Do not create an empty `images/` directory as a placeholder; empty directories are an error.

When a photo is wanted, hand off to `design-visual-cookbook-image-generator`. The canonical file is `images/{slug}.jpg` and nothing else. The `-sidebar` and `-spread` crops are derived — run `cookbook fit` to produce them, and never hand-edit or commit them.

### Step 6: Verify it actually renders

Source review is not sufficient. The parser silently drops content it does not recognize, so a malformed entry looks fine in Markdown and comes out blank on the page.

```bash
cookbook lint                    # structural check; must be clean
cookbook build --only {slug}     # render just this entry
cookbook index                   # refresh index.md
```

Open `draft/cookbook-draft.html` and look at the page. Confirm the title, attribution, every ingredient, and every direction step are present, and that nothing is clipped at the bottom.

Then rebuild the whole book (`cookbook build`) and check the page count moved as expected. Adding an entry shifts pagination for everything after it, and section dividers are forced onto right-hand pages — so one new recipe can add two pages, not one.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Recipe entry format | `.github/instructions/recipe-content.instructions.md` | Writing the clean `recipe.md` — required sections, metadata keys, transcription rules (Step 4) |
| Page entry format | `.github/instructions/book-pages.instructions.md` | The entry is not a food recipe (Steps 1, 4) |
| Chapter list | `book/book.yaml` | Choosing a chapter, or being asked to add one (Step 2) |
| Structural rules | `cookbook lint` | Understanding what the automated check will and will not catch (Step 6) |
| Photo generation | `design-visual-cookbook-image-generator` | Only when a photograph is wanted for the entry (Step 5) |

## Constraints

### MUST DO

- Write the verbatim transcription to `sources/` before writing the clean entry, whenever an original document exists.
- Preserve the source's wording, gaps, and family voice; normalize structure only.
- Mark illegible passages explicitly and report them to the user by entry name.
- File food recipes under `book/recipes/` and all prose under `book/sections/`, including front and back matter.
- Use a lowercase kebab-case slug, checked against existing slugs in the category first.
- Include `## Ingredients` and `## Directions` in every recipe, even when the source is unstructured prose.
- Keep Directions as one sequentially numbered list, with phase names folded into step text.
- Name the canonical photograph `images/{slug}.jpg` and run `cookbook fit` after adding it.
- Render the entry and inspect it visually before calling the ingestion done.
- Run `cookbook lint` and `cookbook index` after ingesting.

### MUST NOT DO

- Invent an amount, temperature, time, yield, or ingredient the source does not state.
- Rewrite the family's phrasing into neutral instructional prose.
- Write a `sources/` file that is really a copy of your cleaned-up version.
- Create an empty `images/`, `sources/`, or `prompts/` directory as a placeholder.
- Add a new category without saying what it requires (a folder plus a block in `book/book.yaml`) and confirming first.
- Hand-edit or commit the derived `-sidebar`/`-spread` crops.
- Link `sources/recipe-original.md` when no such file was written.
- Declare the entry done on a source read alone, without rendering it.

## Knowledge Reference

Recipe transcription, verbatim source archive, OCR artifact correction, family voice preservation, recipe normalization, ingredient list structuring, direction step sequencing, sub-recipe subheads, recipe metadata chips, entry slug, category routing, food recipe vs. book page, canonical dish photograph, derived image crops, layout auto-assignment, focused draft render, structural lint, generated index

## Done When

- The entry folder holds a clean `recipe.md`/`page.md`, and `sources/` when an original exists.
- No empty directories were created.
- `cookbook lint` reports no errors.
- The entry was rendered and visually inspected, not just read as Markdown.
- `index.md` was regenerated.
- Any transcription gaps or judgment calls were reported to the user by name, so a human can check them against the original.
