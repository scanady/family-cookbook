---
name: cookbook-build
description: 'Build the cookbook — a screen draft for review, or the press-ready interior and cover PDFs for a print vendor — running the overflow check, compressing the interior, and confirming the trim, bleed, gutter, and page-count requirements before upload. Use when asked to "build the cookbook", "render the draft", "make the print PDF", "export the book", "prepare files for Lulu", or "is this ready to send to the printer".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: cookbook-lint, cookbook-recipe-ingest
---

# Cookbook Build And Print Preparation

Turn `book/` into either a draft to look at or a pair of PDFs a printer will accept.

## Role Definition

You are running pre-press. The failure mode here is not a crash — it is a file that uploads cleanly, passes preflight, gets printed, and arrives with the last line of a recipe cut off. Every check below exists because something can go wrong silently.

## When To Use

Use this to render the book at any fidelity: a quick draft after an edit, a focused single-entry render, or the full press-ready output before ordering copies.

Do not use it to fix content problems it surfaces — overflow and structural errors go back to `cookbook-lint` or the entry itself.

## Build Modes

### Screen draft — the default

```bash
cookbook build                   # whole book
cookbook build --only slug1,slug2 # just these entries
```

Writes `draft/cookbook-draft.html` at 8×11in trim with no bleed. Open it in a browser. This is the mode for reviewing content and layout. It is paginated like the printed book and laid out as open spreads (page 1 alone on the right, then 2|3, 4|5), so a two-page recipe shows as its spread — in an `--only` build too, which pads with a blank leaf where a spread needs one. An `--only` build replaces the whole-book draft with just those entries; run `cookbook build` again to see the whole book.

**Always inspect the rendered page, not just the Markdown.** The parser drops content it does not recognize, so an entry can look correct in source and render with its directions missing.

### Press-ready interior

```bash
cookbook build --print
cookbook check
```

`--print` switches to 8.5×11in trim plus 0.125in bleed on all sides — page box 8.75×11.25in — with a mirrored binding gutter so the inner margin falls on the correct side of each leaf.

`cookbook check` must print `No overflow` (exit 0) before you go further; it exits 1 when any page overflows or prints reading text — ingredients, directions, notes, prose — below 10 pt. It loads the print HTML in Chromium and reports any page whose content escapes the page box, and any page whose reading text the renderer's auto-shrink took under 10 pt. **This is the check that catches text cut off or shrunk in the final PDF**, and there is no substitute for it — reading the Markdown will not find these.

If it reports overflow or small text, stop and fix it. The renderer auto-shrinks overflowing pages, so an offending page may not look broken; it will just be typeset noticeably smaller than its neighbors. That is a signal the entry wants a different archetype — usually a two-page one: the Two-Page Spread when the whole recipe fits a full page of text facing its photo, the Recipe Spread when it is longer than that.

Then export and compress:

```bash
cookbook export interior
```

This writes the raw `draft/cookbook-interior.pdf` (Chromium over CDP; Chrome's command-line print path crashes on a document this long) and then compresses it with Ghostscript to `draft/cookbook-interior-press.pdf`, the file you actually upload. The compression flags are built in and encode the vendor's 300 PPI sRGB requirement. It needs Chromium (`python -m playwright install chromium`) and Ghostscript (`gs`), and fails with a clear message if either is missing.

### Cover

```bash
cookbook cover
cookbook export cover
```

The spine width comes from the interior page count. `cookbook cover` lays the book out the same way the interior build does, looks the count up in Lulu's hardcover spine table, and prints the page count and spine it used: `Casewrap: W x H in (spine S in for N pages, Lulu hardcover table)`. A few added recipes can cross a spine band, so rebuild the cover after every interior change, never before. After uploading the interior, compare the printed spine with the cover template Lulu generates. If they differ, do not upload the mismatched cover: report it as an issue at https://github.com/scanady/family-cookbook/issues with the page count and Lulu's spine value.

Cover copy, accent, spine text, and front photo come from `book/book.yaml` (`book:` and `cover:`); the back-cover blurb and sign-off are prose in `book/cover.md`.

### The whole press sequence

```bash
cookbook press
```

Runs lint → fit → build --print → check → export interior (with compression) → cover → export cover, and stops at the first failure. Lint runs first: when it reports any error — including leftover `TODO` placeholder text from `cookbook init` in `book/**/*.md` or `book.yaml` — press prints the errors and stops before building anything. Fix them and run it again.

## Before Any Press Build

```bash
cookbook lint                    # must exit clean; leftover TODO placeholders are errors
cookbook fit                     # refresh derived crops
cookbook index                   # keep index.md honest
```

`cookbook fit` regenerates the `-sidebar` and `-spread` crops, each centered on the dish it finds in the photo. Band and hero photos have no crop file: their height is whatever the text leaves, so the page carries the canonical image and the browser frames it once that height is known; the Recipe Spread's photo works the same way. Run it after any image or archetype change. It reports photos too low-resolution for crisp print at their placed size, and placed frames that cut the dish — give such a recipe a `layouts:` row with a frame that holds it. Both are worth knowing about before you pay for copies.

## Page Count And Pagination

Section dividers are forced onto recto (right-hand) pages, a blank leaf is auto-inserted before any that would land on a verso, and the book is padded to an even total. A book shorter than Lulu's 24-page hardcover minimum is padded with blank pages to reach it, and the build summary says so. Two-page recipes (Two-Page Spread, Recipe Spread) always start on a verso so the pair faces; the next one-page recipe of the chapter moves in front of the pair, or a blank fills the slot. This is why the raw entry count and the final page count differ. The screen draft paginates the same way, so its count matches the print build's.

Watch the count between builds. A content change that moves the count by more than it should has crossed a divider over a recto boundary and inserted or dropped a blank leaf.

## Before Uploading

Check the interior against the vendor specification table in [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md): trim, page size with bleed, safety margin, gutter, even page count, embedded fonts, image resolution, color space, no transparency, no trim marks, no encryption.

Then order **one proof copy** and go through the proof checklist in [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) before ordering more. Screen review does not catch a gutter that swallows the inner edge of a photo.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Vendor specification | [The engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) | Any press build — the spec table, cover geometry, and upload order |
| Renderer geometry | The engine's `render.py` | Diagnosing pagination, trim, bleed, or gutter behaviour |
| Cover geometry | The engine's `cover.py` and `lulu.py` | Building the cover; Lulu's hardcover spine table |
| Structural check | `cookbook lint` | Before any press build; `cookbook press` runs it first |
| Content defects | `cookbook-lint` | Overflow or structural errors surface and need fixing |

## Constraints

### MUST DO

- Run `cookbook lint` clean before any press build.
- Run `cookbook check` against the print HTML and require `No overflow` before exporting.
- Refresh derived crops with `cookbook fit` after any image or archetype change.
- Export with `cookbook export interior` (or `cookbook press`); its built-in compression flags encode the vendor's resolution and color requirements.
- Rebuild the cover after the final interior build, and check its spine against the template Lulu generates after the interior upload.
- Check every row of the specification table in [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) before upload.
- Inspect the rendered pages, not the Markdown.
- Explain any page-count change between builds.

### MUST NOT DO

- Export a PDF while `cookbook check` reports overflow.
- Upload a cover built from an older interior, or one whose spine disagrees with Lulu's template.
- Upload the uncompressed interior.
- Treat a page that passes the overflow check as well set — auto-shrink hides a too-dense page.
- Fix content defects here; send them back to the entry or to `cookbook-lint`.
- Order a full print run before a proof copy has been checked in hand.

## Knowledge Reference

Screen draft render, press-ready interior, trim size, print bleed, safety margin, mirrored binding gutter, recto-forced section divider, even page count, overflow check, Chromium print-to-PDF, CDP printToPDF streaming, Ghostscript recompression, 300 PPI sRGB, embedded font outlines, casewrap cover wrap, Lulu hardcover spine table, vendor cover template, proof copy

## Done When

- `cookbook lint` is clean and `cookbook check` reports `No overflow`.
- The interior PDF is compressed, and its page count matches what the draft build reported.
- The cover was rebuilt after the final interior, and its spine matches Lulu's template.
- Every row of the specification table in [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) is satisfied.
- A proof copy is ordered and checked against the proof checklist in [the engine's printing guide](https://github.com/scanady/family-cookbook/blob/main/docs/PRINTING.md) before any full run.
