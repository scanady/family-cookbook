# Changelog

## 1.3.0

Windows is supported, and its installer is the one the README shows first.

- **`install.ps1`**, run from PowerShell with
  `irm https://raw.githubusercontent.com/scanady/family-cookbook/main/install.ps1 | iex`:
  installs Python if there is none (through winget), the engine, Chromium, and
  Ghostscript (its own installer, one permission prompt), starts the book, asks
  for the AI service and key, and writes a `cookbook.cmd` launcher, so
  `./cookbook studio` works in PowerShell as it does in a macOS or Linux
  terminal. CI runs it under Windows PowerShell 5.1 and prints a new book.
- **The engine on Windows.** Ghostscript is found as `gswin64c`, on PATH or
  under Program Files, where its installer leaves it. Output to the console
  and from poppler is read and written as UTF-8. `.claude/skills` and
  `.github/skills` become copies of `.agents/skills` where Windows refuses
  links. `.env` may start with a byte-order mark. `cookbook doctor` gives the
  Windows command for each fix.
- Both installers install the release's source archive, so git is no longer
  needed.

## 1.2.1

- `install.sh` asks which AI service to use, OpenRouter (recommended), Google
  AI Studio, or none, then asks for that service's key. It warns when an
  OpenRouter key does not start `sk-or-`.
- The "AI is off" message, `cookbook doctor`, the new book's `.env`, and the
  README list OpenRouter first.

## 1.2.0

- **OpenRouter.** `OPENROUTER_API_KEY` in the book's `.env` turns AI on
  without a Google account: `ingest` and `photo` reach the same Gemini models
  through OpenRouter, paid from prepaid credits. With both keys, Gemini is
  used. `--model` and `--image-model` also take any OpenRouter model id
  (`vendor/model`). The cost OpenRouter reports goes to the AI log.
- `install.sh` takes either key and saves it under the right name;
  `cookbook init` writes both lines into `.env`; `cookbook doctor` names the
  service in use.

## 1.1.0

Getting started takes one command, and AI is on by default.

- **`install.sh`** sets up a book in one step: the engine in the folder's own
  virtual environment, Chromium, a new book (it asks for the title and
  subtitle), the Gemini key (optional), and a `./cookbook` launcher that needs
  no activated virtual environment. Run it again to upgrade.
- **AI is part of the install.** `google-genai` is a regular dependency; the
  `ai` extra is gone.
- **No key, no stop.** Without `GEMINI_API_KEY`, `cookbook ingest` warns and
  files the pages as one recipe to type up beside the card in the studio
  (`--title` names it), and `cookbook photo` warns and makes nothing.
- **`cookbook doctor`** checks Chromium, Ghostscript, poppler, the AI key, and
  the book folder, and prints the command that fixes each one missing.
- **`cookbook init`** writes `.env` (empty key, ignored by git) instead of
  `.env.example`, defaults `--categories` to `breakfast,mains,sides,desserts`,
  and ends with the next commands to run.
- **Docs.** The README covers install and the five commands most books need;
  the full command reference moved to `docs/COMMANDS.md`, troubleshooting and
  the glossary to `docs/TROUBLESHOOTING.md`.

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
