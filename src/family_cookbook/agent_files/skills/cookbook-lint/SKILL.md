---
name: cookbook-lint
description: 'Review the cookbook spec in book/ for everything that would render wrong or read wrong — broken structure, stale layout rows, orphan images, missing attributions, inconsistent voice, and pages whose content overflows the trim — then fix what is safe to fix and report the rest. Use when asked to "lint the cookbook", "review the book spec", "check the cookbook is in order", "audit the recipes", or "is the book ready to print".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: cookbook-recipe-ingest, cookbook-recipe-remove, cookbook-build
---

# Cookbook Spec Review

Check that everything in `book/` is in order — mechanically, editorially, and typographically — and report what is not.

## Role Definition

You are a copy editor and production checker on a book that is about to be printed and given to family. Two failure modes matter and they are different: things that are *wrong* (a recipe that renders blank, a manifest row pointing at nothing) and things that are *inconsistent* (three recipes crediting the same person three different ways). The script finds the first kind. You find the second.

## When To Use

Use this before a print run, after a batch of ingestions, after any restructuring, or whenever asked whether the book is in good shape.

## Workflow

### Step 1: Run the structural linter

```bash
cookbook lint
```

This is the mechanical pass. It checks entry structure, required sections, sequential direction numbering, image links that resolve, canonical image naming, orphan files in `images/`, empty directories, and source-link consistency; then `book/book.yaml` — stale and duplicate layout rows, unknown archetype names, unresolvable spec paths, chapters declared with no folder on disk, malformed accent colors, a missing cover photo, chapters absent from the book order, dividers that name nothing, and dead `pinned` entries.

It also enforces the configuration/content boundary in both directions: prose fields added back to `book.yaml`, and markdown pages whose copy of a name no longer matches the config — a divider whose H1 has drifted from its chapter label, or a title page still carrying the old book title or edition. Those are the failures that reach print, because both halves look correct in isolation.

Leftover placeholder text is an error: any line containing `TODO` in `book/**/*.md` (the cover, dividers, and front and back matter included) and any `TODO` in a `book.yaml` string value, such as the subtitle `cookbook init` writes. Lint names the file and line. Replace each with the family's real text. A chapter in `book.yaml` with no entries and an unknown top-level key in `book.yaml` (a leftover `print:` block, say) are warnings.

`cookbook press` runs this linter first and stops before any build when it reports errors, so a clean lint is the price of a print run.

Keepsakes get their own pass: an `extras/extras.md` that lists a missing or unsupported file, or nothing at all, is an error; files it does not list ("not printed"), an `extras/` without `extras.md`, a missing caption, an image too small for where it lands, PNG transparency, and an `extras:` layout override that cannot apply are warnings. `cookbook-extras` owns the fixes.

A malformed `book.yaml` fails earlier and harder: the loader refuses to run at all, and every script that reads it exits with the reason rather than a traceback.

Errors fail the build's correctness; warnings are judgment calls. Fix errors. For each warning, decide whether it is a real problem or an accepted exception, and say which.

Do not paraphrase the linter's output back to the user as your review. It is the starting point, not the finding.

### Step 2: Confirm the book renders

```bash
cookbook build
```

Note the page count and the archetype distribution it prints. Compare against the last known-good numbers. A page count that moved without a content change means pagination shifted — usually a divider crossing a recto boundary.

### Step 3: Check for content that overflows the page

```bash
cookbook build --print
cookbook check
```

`cookbook check` must print `No overflow`. This is the check that catches text cut off in the printed PDF, and it is the one that cannot be done by reading Markdown — a recipe that looks unremarkable in source can spill past the trim once it is typeset.

The renderer auto-shrinks overflowing pages, so a page that passes may still have been scaled down noticeably. Open the draft and look for any page whose type is conspicuously smaller than its neighbors; that recipe is a candidate for a different archetype or a second page.

Then run the content checks, with the overflow check folded in:

```bash
cookbook audit --check
```

It writes `draft/book-report.html`: every entry's findings, errors first, with page links. Its checks: a transcription or last step cut off mid-sentence, or an empty ingredient list; a Cook time no stated stage supports, or a Temperature the directions contradict; a Yield, Prep time, Temperature, or ingredient amount the source does not state (invented; a book that keeps its own "About …" estimates sets `audit: estimates: true` in `book.yaml`, which you never change without the family's say); a food the method uses that the list does not name; an ingredient line that says what the source does not, or holds a step of the method; marks the transcription left; a line of the source dropped from the recipe; a source that gives no method; credits that probably name one person; a phone number, email, or street address in printed text. It also carries lint, the photo rules, and `cookbook check`. Settle every error and warning against the entry's `sources/`; a finding the source proves wrong is an accepted exception, said so in your report.

### Step 4: Review what the script cannot check

Read the entries themselves. Look for:

**Attribution consistency.** `cookbook audit` flags credits that probably name one person (a nickname, a short form, a one-letter spelling difference). Read the contributors page too: a maiden and a married name, or `Grandma` for a named cook, is the same person in a way no check can see.

**Missing attribution.** An entry with no `*Name*` line is either a genuine orphan or an oversight. Flag them; do not guess a name.

**Category fit.** A recipe filed somewhere odd renders in the wrong section under the wrong color accent. Skim each category's entries and ask whether each belongs.

**Voice.** These recipes were normalized from family handwriting, and the point was to keep the family voice. Flag any entry that reads as though it were rewritten into neutral instructional prose — that is a fidelity regression, not a style improvement.

**Fabrication risk.** `cookbook audit` flags metadata and amounts the source does not state. For an entry with no `sources/recipe-original.md` it cannot: check those by asking where the detail came from. Invented specifics are the worst defect this book can have.

**Layout variety.** Read `book/book.yaml` alongside the draft. Adjacent pages sharing both an archetype and an image zone read as repetitive. The auto-assigner varies them, but curated rows can collide.

### Step 5: Fix and report

Fix mechanical problems directly: stale manifest rows, empty directories, broken links, numbering, missing required sections.

Do not fix editorial ones silently. Attribution spellings, category moves, and anything touching recipe wording are the family's call — propose them and let the user decide.

Report as a short list ordered by severity, each item naming the file. Distinguish clearly between what you changed and what you are recommending.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Automated structural rules | `cookbook lint` | Interpreting the mechanical pass and deciding what it cannot cover (Steps 1, 4) |
| Content checks and book report | `cookbook audit --check` → `draft/book-report.html` | Truncation, cook times, invented figures, missing ingredients, dropped lines, same-cook credits, personal data (Step 3) |
| Recipe conventions | `.github/instructions/recipe-content.instructions.md` | Judging whether an entry follows the format (Step 4) |
| Page conventions | `.github/instructions/book-pages.instructions.md` | Reviewing non-recipe pages and dividers (Step 4) |
| Layout and manifest conventions | [The engine's layout instructions](https://github.com/scanady/family-cookbook/blob/main/.github/instructions/cookbook-layout.instructions.md) | Reviewing layout variety and curated rows (Step 4) |
| Print specification | [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) | The review is a pre-press check before a print run (Step 3) |
| Fixing an entry | `cookbook-recipe-ingest` | A finding requires re-transcribing or refiling an entry |

## Constraints

### MUST DO

- Run `cookbook lint` first, and treat its output as the starting point rather than the finding.
- Resolve every error; for each remaining warning, state whether it is a real problem or an accepted exception.
- Build the book and run `cookbook audit --check` before calling the book print-ready: it includes `cookbook check`.
- Read the entries themselves — missing attribution, category fit, voice, and layout variety are not automated.
- Settle every `cookbook audit` finding against the entry's source, fixing it or naming it an accepted exception.
- Report findings ordered by severity, each naming its file.
- Separate what you changed from what you are recommending.

### MUST NOT DO

- Paraphrase the linter's output back as the review.
- Change attribution spellings, move entries between categories, or reword recipe text without the user's decision.
- Treat a clean linter run as evidence the book is ready — overflow and editorial defects sit outside it.
- Treat a passing overflow check as evidence a page is well set; auto-shrink hides a too-dense page.
- "Improve" family voice into neutral instructional prose.

## Knowledge Reference

Structural lint, editorial review, attribution consistency, missing attribution, category fit, family voice fidelity, fabricated detail, orphan image file, empty directory, sequential direction numbering, stale manifest row, unknown layout archetype, page overflow check, auto-shrink typesetting, layout variety, pre-press readiness

## Done When

- `cookbook lint` exits clean, or every remaining warning is explained as accepted.
- The book builds and `cookbook check` reports `No overflow`.
- Every `cookbook audit` error and warning is fixed or named as an accepted exception.
- The editorial pass covered attribution, category fit, voice, and layout variety.
- The user has a severity-ordered report separating changes made from changes proposed.
