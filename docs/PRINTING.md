# Printing the cookbook at Lulu

Target product: **Lulu Hardcover, Casewrap, US Letter (8.5 × 11 in), Premium Color on 80# Coated White, perfect-bound book block.** Cover finish (gloss or matte) does not change the files: choose it at Lulu.

Everything below is produced by the `cookbook` command, run from your book's
root. You build the two PDFs, then upload them in Lulu's Project Creation
tool.

## Prerequisites

- The engine installed (see the [README](../README.md#install), or
  [install by hand](COMMANDS.md#install-by-hand)), or its
  [container image](COMMANDS.md#in-a-container), which has everything below.
- Chromium for Playwright and Ghostscript (`gs`) on your `PATH`, for the
  interior compression.

`cookbook doctor` checks for both and prints the command that installs either
one missing; `cookbook press` fails with a clear message without them.

## Build the two files

```bash
cookbook press
```

`cookbook press` runs the whole sequence and stops at the first failure. It
starts with `cookbook lint` and builds nothing while lint reports errors, such
as placeholder `TODO` text left from `cookbook init`:

```bash
cookbook lint                 # must report no errors
cookbook fit                  # refresh layout-fitted photo crops
cookbook build --print        # -> draft/cookbook-print.html; prints "Pages: N (...)"
cookbook check                # must exit 0: no overflow, no reading text < 10pt
cookbook export interior      # -> draft/cookbook-interior.pdf, then draft/cookbook-interior-press.pdf
cookbook cover                # -> draft/cookbook-cover.html; prints the casewrap size and spine
cookbook export cover         # -> draft/cookbook-cover.pdf
```

**Upload `cookbook-interior-press.pdf`** (images recompressed to 300 PPI sRGB
JPEG — typically a tenth of the raw file's size, visually identical) and
`cookbook-cover.pdf`.

`cookbook export interior` and `cookbook export cover` drive Playwright's
Chromium over CDP with a streamed `printToPDF`, because Chrome's command-line
print path crashes on a document this long and the uncompressed interior is too
large for Playwright's ordinary `page.pdf()`. The interior is then compressed
with Ghostscript; for reference, the command it runs is:

```bash
gs -q -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -dCompatibilityLevel=1.6 \
  -sColorConversionStrategy=sRGB -dProcessColorModel=/DeviceRGB \
  -dAutoFilterColorImages=false -dColorImageFilter=/DCTEncode -dJPEGQ=90 \
  -dDownsampleColorImages=true -dColorImageResolution=300 -dColorImageDownsampleThreshold=1.0 \
  -dDownsampleGrayImages=true -dGrayImageResolution=300 \
  -o draft/cookbook-interior-press.pdf draft/cookbook-interior.pdf
```

`cookbook check` loads the print HTML in Chromium and reports any page
whose content sticks out of the page box, and any page whose ingredient or
direction text — or any note or prose line — prints below **10 pt** once `FIT_SCRIPT`'s zoom is applied —
run it after content edits; cut-off or shrunken text shows up here first. A
recipe that only fits one page below 10 pt belongs on a two-page layout — the
Two-Page Spread or the Recipe Spread (see [LAYOUTS.md](LAYOUTS.md)).

Fonts are embedded as vector outlines (see notes).

## Interior specs (what the files already satisfy)

| Spec | Lulu requirement | This file |
|------|------------------|-----------|
| Trim size | 8.5 × 11 in | ✅ |
| Page (PDF) size | trim + 0.125 in bleed all sides = **8.75 × 11.25 in** | ✅ every page |
| Bleed | 0.125 in; art/background must fill it | ✅ paper + Hero photos fill bleed |
| Safety margin | 0.5 in inside trim | ✅ text set 0.75 in from the trim at the top and outer edge and 0.875 in at the bottom (`MARGIN_IN`, `MARGIN_BOTTOM_IN`): cookbook margins, wider than the minimum. The folio sits on the 0.5 in safety line (`FOLIO_IN`), in clear paper below the last text line |
| Binding gutter | inside margin by page count: up to 150 pages is covered by 0.75 in; 151–400 pages need 1 in | ✅ up to 150 pages: 0.75 in from trim, **mirrored** by recto/verso. `cookbook build --print` warns when the page count needs a wider inside margin; for a book past 150 pages, [open an issue](https://github.com/scanady/family-cookbook/issues) with the page count before printing |
| Page count | even; hardcover needs 24–800 | ✅ padded to even, and a book under 24 pages is padded with blank leaves at the back; `cookbook build --print` prints `Pages: N (...)` (incl. recto-opener and two-page-recipe blanks) |
| Fonts | embedded or converted to outlines | ✅ embedded as vector outlines |
| Images | 300 PPI min, ≤ 600 PPI | ✅ 300 PPI after the press compression step (every photo) |
| Color | sRGB or CMYK | ✅ sRGB (Chromium output) |
| Transparency | flatten / remove | ✅ none (opaque hero panels, square image corners) |
| Marks | no trim/bleed marks | ✅ none |
| Security | no password/encryption | ✅ none |

Section dividers are forced onto **recto (right-hand) pages**; a blank leaf is
auto-inserted before any that would land on a verso, and the book is padded to
an even total. Two-leaf recipes (Two-Page Spread, Recipe Spread) always start on
a **verso**, so the pair faces across the gutter: the next ordinary recipe of
the same chapter is lifted in front of the pair, or a blank is inserted when
none is left. This is why the page count includes blank leaves. The screen
draft is paginated the same way and laid out in spreads, so what you review is
what binds.

### A note on fonts (Type3 vector outlines)

Chromium's PDF output writes each glyph as a **Type3 font built from vector
path operators** — i.e. the text is embedded as resolution-independent
**outlines** (`pdffonts` lists them as embedded Type 3). This meets Lulu's
"embedded or converted to outlines" rule and prints identically to live text.
Trade-off: the PDF's text is not selectable/searchable (fine for a print
interior). If a future Lulu preflight ever objects to Type3 specifically, the
interior needs a renderer that embeds TrueType subsets.

## Cover specs (casewrap)

The casewrap wrap is one wide sheet folding over both boards + the spine:

```
total width  = 0.75 turn-in + 8.625 back board + SPINE + 8.625 front board + 0.75 turn-in
             = 18.75 + SPINE
total height = 0.75 turn-in + 11.25 board + 0.75 turn-in = 12.75
(board = 8.5 trim + 0.125 overhang;  height board = 11 + 0.25 overhang)
```

`cookbook cover` prints the result for your book:
`Casewrap: W x 12.750 in (spine S in for N pages, Lulu hardcover table)` —
W is 18.75 + S. Confirm N and S against the cover template Lulu generates.

### Spine width

`cookbook cover` lays the book out to get the interior page count, then looks
the spine up in Lulu's hardcover table (Lulu Book Creation Guide, "Spine Width
Calculations"), which the engine keeps in `src/family_cookbook/lulu.py`;
each band of page counts maps to one spine width. It
prints the page count and spine it used. Adding a few recipes can cross a band,
so always rebuild the cover after the interior.

Lulu generates its own cover template after you upload the interior. Compare
its spine width with the one `cookbook cover` printed; if they ever differ,
[open an issue](https://github.com/scanady/family-cookbook/issues) with the page
count and Lulu's spine width. The 0.75
in turn-in and Lulu's ±0.0625 in tolerance absorb small differences, but a
matching spine keeps the front and back art centered on their boards.

## Upload order at Lulu

1. Create a new **Print Book** → Hardcover → Casewrap → US Letter 8.5 × 11 →
   Premium Color → 80# Coated White. Choose gloss or matte for the cover.
2. Upload `cookbook-interior-press.pdf`. Confirm the page count matches
   the `Pages: N` that `cookbook build --print` reported, and no preflight errors.
3. Download Lulu's generated cover template and check its spine (above).
4. Upload `cookbook-cover.pdf`.
5. Order a **single proof copy** and check it against the list below before
   ordering more.

## Checking the proof copy

Lulu trims within ±0.125 in, so judge edges against that tolerance, not
against the screen.

**Cover**
- Spine text is centered on the spine and does not wrap onto either board.
- The front photo is sharp and the accent color matches the interior.
- Nothing important sits within 0.5 in of a trimmed edge or the hinge.

**Binding and gutter**
- The book opens far enough to read the inside lines of every page without
  forcing the spine; no text disappears into the gutter.
- Two-page recipes: the photo's subject and the first column of text both
  clear the binding.

**Type and reading at the stove**
- Ingredients and directions read comfortably at arm's length — the 10 pt
  floor, on the actual paper.
- Notes and attributions (lighter gray) are still legible.
- Page numbers sit clear of the text and the trim.

**Photos and color**
- Food looks appetizing: no muddy shadows, no color cast, no visible
  compression blocks in the full-page photos.
- Crops show the whole dish; no subject is cut at a trimmed edge.
- Accent colors (chapter rules and headings) match from chapter to chapter.

**Structure**
- Chapter openers fall on right-hand pages; the blank pages are where they
  should be.
- Contents and contributors page numbers match the printed pages (spot-check
  ten).
- Dedication, closing message, and the family's own lines read as written.

Record every defect with its page number. Fix them in `book/` (or
[open an issue](https://github.com/scanady/family-cookbook/issues) for a layout
problem you cannot fix there), rebuild, and order a second proof only if a
defect changed layout or color.

## Editing cover content

The title, subtitle, edition, spine text, accent color, and front photo come
from `book/book.yaml` (`book:` and `cover:`, see [BOOK-YAML.md](BOOK-YAML.md#cover));
the back-cover blurb and sign-off are prose in `book/cover.md`. The spine width
comes from the page count, as above.
