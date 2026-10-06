# Changelog

## 1.0.0

First public release, under the PolyForm Noncommercial License 1.0.0: free for
any noncommercial use, including making your own family's cookbook. Earlier
versions were private.

What the engine does:

- **Lays out a book** from `book/book.yaml` and markdown recipes and pages:
  chapters opening on right-hand pages, a generated title page, contents,
  contributors, and an optional index; seven page layouts chosen automatically
  per recipe, two facing pages for long recipes, photos cropped around the
  dish, keepsake scans inset or on their own page. `cookbook build` makes a
  draft to read in the browser.
- **Makes the print files** with `cookbook press`: the interior PDF (US Letter
  with bleed, mirrored gutter, 300 PPI images, fonts embedded) and the casewrap
  cover with a spine sized from the page count, to Lulu's hardcover
  specification. `docs/PRINTING.md` covers uploading to Lulu and checking the
  proof copy.
- **Checks the book** before it prints: `cookbook lint` (structure, and
  placeholder text left from `cookbook init`), `cookbook check` (no text cut
  off at a page edge, nothing below 10 pt), `cookbook fit` (photo crops and
  resolution), and `cookbook audit` (content checks against each recipe's
  original, in one book report). `cookbook press` runs lint first and stops
  while it reports errors.
- **Reads recipe cards** with an AI model (`cookbook ingest`, photos and PDFs),
  **generates dish photos** (`cookbook photo`), and puts each recipe beside its
  original for review (`cookbook review`). These need the `ai` extra and a
  Gemini API key in the book's `.env`; each call's cost is logged to
  `book/sources/ai-log.jsonl`.
- **The studio** (`cookbook studio`): a local web page for reviewing recipes,
  ordering chapters, adding keepsakes, reading the book report, and making the
  print files.
- `cookbook init` starts a book; `cookbook agent-files` installs guides for AI
  coding assistants; a `Dockerfile` runs the engine without installing its
  dependencies.
- An example book, `examples/fannie-farmer-1896`, with four deliberate content
  defects for trying the review.
