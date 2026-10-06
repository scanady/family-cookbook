---
name: cookbook-extras
description: 'Add keepsakes to the family cookbook — scans of original recipe cards, family photos, letters — by reviewing what a family member dropped into an extras/ folder, captioning it, listing it in extras.md, and confirming it prints well inset on the page or on a keepsake page. Use when asked to "add Ruth''s card to the book", "put this photo with the recipe", "I dropped some scans in extras", "review the extras", or "caption these keepsakes".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: cookbook-recipe-ingest, cookbook-lint, cookbook-build
---

# Cookbook Extras

Put the family's keepsakes in the book beside the recipes they belong to: the stained original card, Ruth at the stove, the letter that came with the cake. The family's job is to drop files into a folder. Yours is to decide which ones print, caption them truthfully, and make sure each one prints well.

## Role Definition

You are the archivist reviewing a shoebox someone handed over. Nothing in it is yours to discard, and nothing goes to print without a look. A blurry scan or a guessed caption looks worse in a printed heirloom than a missing one, so the review step is where this skill earns its keep.

## When To Use

Use this when someone adds card scans, photos, or letters to an `extras/` folder, asks to put one in the book, or asks for the extras to be reviewed.

Do not use it to transcribe what a card says — that is `cookbook-recipe-ingest`, which writes `sources/`. A scan in `extras/` is the card as a picture; its words still belong in the transcription. Do not use it for the finished-dish photo either; that is `images/{slug}.jpg`.

## How Extras Work

An `extras/` folder can sit in two places:

| Folder | Prints with |
|--------|-------------|
| `book/recipes/{chapter}/{slug}/extras/` (or `book/sections/{chapter}/{slug}/extras/`) | that entry |
| `book/sections/{chapter}/extras/` | the chapter's opening page (its divider, or a one-page chapter like the dedication) |

**Only what `extras/extras.md` lists prints**, in the order listed. One markdown image line per item, with the caption as the alt text:

```markdown
# Extras

![Ruth's original card, about 1975](ruth-card.jpg)
![Ruth at the stove on Elm Street, about 1962](ruth-kitchen.jpg)
```

The heading and any notes are ignored, so the family can write reminders there. Files that are not listed stay in the folder safely; `cookbook lint` mentions them as "not printed" so nobody wonders where they went. Supported types: `.jpg` and `.png`.

Placement is automatic and deterministic:

- **Inset** — up to two items along the foot of the entry's own page, when the page has room. Only framed text pages, chapter openers, and short Half-Page Classic recipes have room.
- **Keepsake page** — otherwise, a page right after the entry, items as large as the page allows, captions in italic serif. A landscape item (a recipe card, a group photo) takes the full width; consecutive portraits pair side by side; two such rows per page, so a card prints large enough to read. More items continue onto further keepsake pages, which is why listing order matters. A keepsake page gets a page number and is left out of the contents and index.
- Long recipes on two pages — a Two-Page Spread or a Recipe Spread — always get a keepsake page, right after the spread's second page.

To override, add `extras: inset` or `extras: page` to the entry's row in the `layouts:` list in `book/book.yaml`. If the entry has no row, add one with the archetype it already renders with (shown in the draft's page tag). `inset` is ignored on archetypes that cannot take one; lint says so.

## Workflow

### Step 1: Take the family's drop as it is

A family member only needs to create the `extras/` folder and put files in it — no markdown, no renaming. If they sent files to you instead, put them there yourself, keeping the original files untouched. Rename only to lowercase-kebab-case (`ruth-card.jpg`), never by editing the image.

### Step 2: Inspect every file

Open each image and look at it — do not judge from file names. For each one, decide:

- **Keep** — legible, in focus, worth a reader's attention.
- **Reject as blurry or unreadable** — a card scan whose handwriting you cannot read at full size will not get better in print. Ask for a rescan (300–600 dpi, flat, good light) rather than printing it.
- **Reject as duplicate** — two scans of the same card, a photo and its crop. Keep the better one.
- **Ask** — anything personal or sensitive (a letter, a photo of someone who may not want it published). Confirm with the user before listing it.

Rejecting means leaving it out of `extras.md`, not deleting it. Tell the user which files you left out and why.

### Step 3: Write captions — never invent them

A caption says who, what, and roughly when: `Nora's card, in her own hand, about 1980`. Use what the file, the family member's message, or the recipe's attribution actually establishes. **When you do not know who is in a photo, whose handwriting it is, or when it was taken, ask the user** — never guess a name or a year. "about 1975" is fine when the family said so; it is a fabrication when you inferred it from the paper color.

Keep captions to one short line where possible: they print in 10.5pt italic under the picture. Use typographic apostrophes as the family writes them; markdown `*italic*` works in captions.

### Step 4: List them in `extras.md`

Write `extras/extras.md` with one `![Caption](file.jpg)` line per kept item, in the order they should print — usually the card first, then photos. An `extras.md` that lists nothing is an error; if nothing passed review, leave `extras.md` out and tell the user.

### Step 5: Choose placement

Leave it automatic unless there is a reason not to. Reasons to override:

- A card scan whose writing must be readable → `extras: page`, so it prints large instead of as a 2.3in inset.
- The user explicitly wants the photo on the recipe's page and the page has room → `extras: inset`. Verify in Step 6 that nothing shrank.

### Step 6: Build and look

```bash
cookbook build --only {slug}     # or the chapter name for chapter extras
```

Open `draft/cookbook-draft.html` and check:

- Every listed item appears, in order, with its caption, nothing cropped.
- A card on a keepsake page is readable at that size.
- An inset did not crowd the recipe: ingredients and directions are still full size (lint and `cookbook check` catch shrinking; your eye catches crowding).
- The keepsake page sits directly after its entry.

Then check the print path, since the keepsake page shifts every page after it:

```bash
cookbook build --print
cookbook check
```

### Step 7: Lint

```bash
cookbook lint
```

It errors when `extras.md` lists a file that is missing or not a `.jpg`/`.png`, or lists nothing; it warns about files not listed (not printed), an `extras/` without `extras.md`, a missing caption, an image too small for where it lands (long edge under 700px for an inset, 1500px for a keepsake page), transparency in a PNG, and an `extras:` override that cannot apply. Fix every error; resolve or explain every extras warning.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Folder conventions | `AGENTS.md` (Content Routing) | Deciding where an `extras/` folder goes |
| Placement rules and budgets | The engine's `render.py` (`place_extras`, `INSET_ROOM`) | Explaining why an item landed on a keepsake page |
| Layout override rows | `book/book.yaml` (`layouts:`) | Forcing `extras: inset` or `extras: page` (Step 5) |
| Card transcription | `cookbook-recipe-ingest` | The card's words are not yet in `sources/` |
| Print checks | `cookbook-build`, [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) | Running the press path after adding keepsake pages |

## Constraints

### MUST DO

- Open and look at every file before listing it.
- Leave rejected files in place and tell the user which were left out and why.
- Ask the user for who and when whenever a caption would otherwise be a guess.
- List printed items in `extras/extras.md` only, one `![Caption](file)` line each.
- Build the entry with `--only` and inspect it, then run the print build, `cookbook check`, and `cookbook lint`.
- Confirm the card's words also exist as a transcription in `sources/`; if not, hand off to `cookbook-recipe-ingest`.

### MUST NOT DO

- Invent a name, a date, a place, or a relationship in a caption.
- Edit, crop, retouch, or recompress the family's files.
- Delete a file the family added, even a rejected one, without asking.
- Create an empty `extras/` folder, or an `extras.md` that lists nothing.
- Force `extras: inset` onto a page it crowds; a keepsake page costs a leaf, shrunken recipe type costs the cook.
- Print personal letters or photos of people without the user's confirmation.

## Knowledge Reference

Keepsake page, inset, extras.md listing, curated extras, caption provenance, card scan legibility, rescan resolution, duplicate scan, room budget, layout override, Two-Page Spread, Recipe Spread, print pagination, folio without contents entry, readability floor, unlisted file warning

## Done When

- Every file in `extras/` was inspected; kept ones are listed with truthful captions, the rest are reported to the user.
- No caption contains a guessed name or date.
- The `--only` build shows each item, in order, captioned, uncropped, with the recipe text at full size.
- The print build passes `cookbook check`.
- `cookbook lint` has no errors and no unexplained extras warnings.
