# family-cookbook

Make a printed family cookbook from recipes written in plain text files.

You write each recipe as a small markdown file, or let an AI model type it up
from a photo of the card. Then the `cookbook` command lays out the whole book.
It opens each chapter on a right-hand page and generates a title page,
contents, and contributors. It crops each photo around the dish and gives long
recipes two facing pages. It makes a draft to read in your browser, and the
two PDF files a print shop needs for a hardcover book: the pages and the cover.
The files are made to [Lulu](https://www.lulu.com)'s specification for a
casewrap hardcover, US Letter size (8.5 × 11 in).

![Two facing pages from the example book: Chocolate Cake with a photo across the top of the left page, Indian Pudding with a photo band on the right page](docs/images/example-spread.webp)

*Two pages from the example book in [`examples/fannie-farmer-1896`](examples/fannie-farmer-1896),
recipes from the 1896 Boston Cooking-School Cook Book.*

- [Requirements](#requirements)
- [Install](#install)
- [Quick start](#quick-start)
- [AI features](#ai-features)
- [The studio](#the-studio)
- [Commands](#commands)
- [A book's folder](#a-books-folder)
- [Try the example book](#try-the-example-book)
- [In a container](#in-a-container)
- [Troubleshooting](#troubleshooting)
- [Glossary](#glossary)
- [Getting help](#getting-help) · [Contributing](#contributing) · [License](#license)

Reference: [writing recipes and pages](docs/RECIPE-FORMAT.md) ·
[book.yaml](docs/BOOK-YAML.md) · [page layouts](docs/LAYOUTS.md) ·
[printing at Lulu](docs/PRINTING.md)

## Requirements

- **Linux or macOS.** Windows is not tested.
- **Python 3.11 or newer.**
- **About 700 MB of disk** for Chromium, the browser the engine uses to lay
  out pages and make PDFs. It is downloaded during install.
- **[Ghostscript](https://www.ghostscript.com/)** (`gs`), to make the print
  files: `sudo apt install ghostscript` or `brew install ghostscript`.
- **poppler** (`pdftoppm`, `pdftotext`), only to read recipes from PDF files:
  `sudo apt install poppler-utils` or `brew install poppler`.

## Install

Each book lives in its own folder. Make the folder, and install the engine into
a Python virtual environment inside it:

```bash
mkdir our-cookbook && cd our-cookbook
python3 -m venv .venv
. .venv/bin/activate
pip install "git+https://github.com/scanady/family-cookbook@v1.0.0"
python -m playwright install chromium
```

On Linux, if Chromium will not start later, install the system libraries it
needs: `python -m playwright install --with-deps chromium`.

Run `. .venv/bin/activate` again in each new terminal before using `cookbook`.
`cookbook --version` shows the installed version.

For the [AI features](#ai-features), install the `ai` extra instead:

```bash
pip install "family-cookbook[ai] @ git+https://github.com/scanady/family-cookbook@v1.0.0"
```

To upgrade later, run the same `pip install` line with the new version tag,
then `cookbook agent-files --update` if you use an AI coding assistant.

## Quick start

**1. Start the book.** In the book's folder:

```bash
cookbook init --categories breakfast,mains,desserts --sections kitchen-tips \
    --title "Our Family Cookbook" --subtitle "The Smith Family"
```

`--categories` are the recipe chapters, in order. `--sections` are chapters of
writing rather than recipes, such as family stories or tips. This writes:

- `book/book.yaml`: the chapters, their order and colors, and the cover
  settings ([reference](docs/BOOK-YAML.md));
- a folder for each chapter, with a placeholder opening message;
- placeholder dedication, closing message, and back cover (`book/cover.md`);
- `.gitignore` and `.env.example`;
- guides for AI coding assistants (see [A book's folder](#a-books-folder)).

**2. Add a recipe** at `book/recipes/mains/skillet-cornbread/recipe.md`:

```markdown
# Skillet Cornbread

*Ruth Baker*

![Skillet Cornbread](images/skillet-cornbread.jpg)

- **Yield:** One 10-inch round
- **Cook time:** 20 minutes

## Ingredients

- 1 cup cornmeal
- 1 cup buttermilk

## Directions

1. Heat the oven to 425°F.
2. Bake in a hot skillet until golden, about 20 minutes.

## Notes

- Grandma never measured the fat.
```

Put its photo, if you have one, at
`book/recipes/mains/skillet-cornbread/images/skillet-cornbread.jpg`; the
`![Skillet Cornbread](images/skillet-cornbread.jpg)` line links it. With no
photo, leave that line out: lint reports a link to a missing file as an error.
[RECIPE-FORMAT.md](docs/RECIPE-FORMAT.md) covers every field, photo sizes,
prose pages, and keepsakes. To have an AI model type up the cards instead, see
[AI features](#ai-features).

**3. Look at it.**

```bash
cookbook build
```

Open `draft/cookbook-draft.html` in your browser. It shows the book as facing
pages, the way it will be bound. A small label at the foot of each page names
its layout ([LAYOUTS.md](docs/LAYOUTS.md)); the label is not printed.

**4. Fill in the placeholders.**

```bash
cookbook lint
```

Lint lists every problem in the book's files. On a new book that is the
placeholder text `cookbook init` left: the subtitle if you did not pass one,
the dedication, each chapter's opening message, the closing message, and the
back cover. Replace each with your own words, or delete a chapter message you
do not want. Repeat until lint reports no errors. It also warns about a chapter
with no recipes yet.

**5. Make the print files.**

```bash
cookbook press
```

This checks the book, lays it out at print size, makes sure no text runs off a
page or prints too small, and writes the two files to upload:
`draft/cookbook-interior-press.pdf` (the pages) and `draft/cookbook-cover.pdf`.
It stops at the first problem and says what to fix: for a page that does not
fit, it names the recipe on it and how to make it fit. Expect about 3 seconds a
page.

**6. Print it.** Upload both files to Lulu and order one proof copy first.
[PRINTING.md](docs/PRINTING.md) walks through the upload and what to check on
the proof.

## AI features

Three commands use Google's Gemini models. They need the `ai` extra
([Install](#install)) and a Gemini API key from
[Google AI Studio](https://aistudio.google.com/apikey). Copy `.env.example` to
`.env` in the book's folder and put the key there:

```
GEMINI_API_KEY=your-key-here
```

`.env` is read on every run and never committed (`.gitignore` excludes it). A
`GEMINI_API_KEY` already set in your shell takes precedence.

- **`cookbook ingest`** reads photos, scans, or PDFs of recipe cards and
  cookbook pages. For each recipe it writes a word-for-word copy
  (`sources/recipe-original.md`, with the page images) and a clean
  `recipe.md`. It joins recipes that run across pages. It reports anything it
  had to interpret and every amount it could not find in the original.

  ```bash
  cookbook ingest card-front.jpg card-back.jpg      # one recipe, pages in order
  cookbook ingest old-family-cookbook.pdf --pages 12-30
  ```

- **`cookbook review`** opens a page in your browser to check each typed-up
  recipe against its original, side by side: fix what is wrong, approve, next.
  It uses no AI; it shows what `ingest` flagged and what `cookbook audit`
  finds.

- **`cookbook photo`** makes a photo of a recipe's finished dish. It writes a
  prompt to `prompts/{slug}-image-prompt.md` (edit it if you like), draws the
  photo, and checks it: the whole dish in frame, no text, no extra dishes. It
  tries again, up to three times by default, until the photo fits the book's
  layouts. Earlier attempts are kept in `draft/photos/{slug}/`.

  ```bash
  cookbook photo skillet-cornbread
  ```

**Cost.** Each command adds a line per recipe to `book/sources/ai-log.jsonl`
with the tokens used and the cost in US dollars, so the book's AI spend is on
record. At the October 2026 prices in the engine's price table, each picture
the default image model draws costs about $0.24, so one dish photo costs
$0.24–$0.72 for one to three attempts, plus the text model's calls that write
the prompt and check each picture.

## The studio

```bash
cookbook studio          # opens http://127.0.0.1:8770/
```

The studio is a page in your browser for working on a book that already
exists. Press Ctrl+C in the terminal to stop it. Its tabs:

- **Book**: the draft as facing pages, and a button that rebuilds it.
- **Recipes**: every recipe by chapter with what the checks found. Select one
  to correct it beside its original and approve it.
- **Chapters**: move chapters, and the entries within a chapter, up and down.
  Each move is saved to `book/book.yaml` with its comments kept.
- **Photos & keepsakes**: add a card scan or family photo, with its caption, to
  a recipe or page, or remove one.
- **Report**: the content checks (`cookbook audit`) and their report.
- **Proof**: make the print files (`cookbook press`) and open the two PDFs.

Starting a book (`cookbook init`), adding recipes, and writing the dedication,
chapter messages, and back cover still happen in a text editor, or through
`cookbook ingest`.

## Commands

Run any command from the book's folder or a folder inside it, or pass
`--book PATH`. `cookbook COMMAND -h` lists a command's options.

**Start**

| Command | What it does |
|---|---|
| `cookbook init --categories a,b [--sections x,y] [--title T] [--subtitle S] [--edition E] [--dry-run]` | Start a new book in the current folder (or `--book PATH`). Never overwrites a file. |

**Write and review**

| Command | What it does |
|---|---|
| `cookbook ingest FILE... [--pages P] [--chapter C] [--cook NAME] [--model M] [--dry-run]` | Type up photos, scans, or PDFs of recipes with an AI model. `--chapter` files every recipe in one chapter; `--cook` credits every recipe to one person. |
| `cookbook photo SLUG... [--attempts N] [--new-prompt] [--prompt-only] [--model M] [--image-model M]` | Make a photo of each recipe's finished dish with an AI model. `--prompt-only` writes the prompt to edit first. |
| `cookbook review [--all] [--port N] [--no-open] [--report]` | Check typed-up recipes against their originals in your browser (port 8765). Approvals and time spent go to `book/sources/review-log.jsonl`; `--report` prints the average time per recipe. |
| `cookbook studio [--port N] [--no-open]` | Work on the whole book in your browser (port 8770). |

**Check**

| Command | What it does |
|---|---|
| `cookbook lint [--errors] [--quiet]` | Find mistakes in the book's files: missing sections, broken links, leftover placeholder text. Exits 1 on errors. |
| `cookbook audit [--check]` | Read every recipe for content mistakes and write `draft/book-report.html`, errors first, with links to the pages. It checks for a recipe cut off mid-sentence; a cook time or temperature the directions do not support; a yield, time, or amount the original never states; an ingredient the method uses but the list leaves out; a line of the original left out; and a phone number, email, or street address in printed text. `--check` also runs `cookbook check`. |
| `cookbook check [HTML]` | Find printed pages where text runs off the page or prints smaller than 10 pt, in `draft/cookbook-print.html`. Exits 1 if there are any. |

**Print**

| Command | What it does |
|---|---|
| `cookbook press` | Make the two PDFs to upload: runs lint, fit, build --print, check, export interior, cover, and export cover in turn, and stops at the first failure. |
| `cookbook cover` | Lay out the wraparound cover (back, spine, front) in `draft/cookbook-cover.html`, with the spine sized from the page count. |
| `cookbook export interior` | Turn `draft/cookbook-print.html` into `draft/cookbook-interior.pdf`, then compress it with Ghostscript into `draft/cookbook-interior-press.pdf`. |
| `cookbook export cover` | Turn the cover into `draft/cookbook-cover.pdf`. |

**Advanced**

| Command | What it does |
|---|---|
| `cookbook build [--print] [--only SLUGS]` | Lay out the book in `draft/cookbook-draft.html`. `--print` lays it out at print size, with bleed and binding margin, in `draft/cookbook-print.html`. `--only a,b` replaces `draft/cookbook-draft.html` with just those entries; run `cookbook build` again for the whole book. |
| `cookbook fit [--force]` | Re-crop the photos for their layouts, and list photos too small or badly framed. |
| `cookbook index [--check]` | Rewrite `index.md`, a list of every recipe and page with links, for browsing the book's files. |
| `cookbook agent-files [--update]` | Copy the guides AI coding assistants follow into the book's folder. `--update` replaces them with this version's. |

## A book's folder

```
our-cookbook/
  book/
    book.yaml                          chapters, colors, cover settings, chosen layouts
    cover.md                           back-cover blurb and sign-off
    recipes/{chapter}/{slug}/          a recipe: recipe.md, images/, sources/, prompts/, extras/
    sections/{chapter}/page.md         a chapter's opening message, or a one-page chapter
    sections/{chapter}/{slug}/page.md  a prose entry: a story, a tip, a poem
    sources/ai-log.jsonl               AI tokens and cost per recipe (ingest, photo)
    sources/review-log.jsonl           review approvals and time per recipe
  draft/                               everything the commands make; not committed
  index.md                             written by cookbook index
  .env                                 your GEMINI_API_KEY; not committed
  .env.example                         a template for .env
  .gitignore
  .agents/skills/                      guides for AI coding assistants (cookbook agent-files)
  .claude/skills, .github/skills       links to .agents/skills
  .github/instructions/                the recipe and page format rules, for AI coding assistants
```

A **slug** is an entry's folder name, such as `skillet-cornbread`. The guides
that `cookbook init` and `cookbook agent-files` install let an AI coding
assistant (Claude Code, GitHub Copilot, and others) transcribe recipes, add
keepsakes, and run the checks for you. The `cookbook` command works without
them.

Keeping the book's folder in git is a good way to keep its history; the
`.gitignore` leaves out the generated files and your key.

## Try the example book

The example book is in this repository, not in the installed package. From a
clone:

```bash
git clone https://github.com/scanady/family-cookbook
cd family-cookbook
cookbook build --book examples/fannie-farmer-1896     # draft/cookbook-draft.html
cookbook audit --book examples/fannie-farmer-1896     # draft/book-report.html
cookbook review --book examples/fannie-farmer-1896    # fix them beside the original
```

The example has four mistakes on purpose, the kind an editor fixes in review,
so the report and `cookbook review` have something real to show:

| Recipe | Mistake | Check |
|---|---|---|
| Fish Chowder | Cook time 20 minutes, the first time in the text; the stages add to 45 | cook time |
| Boston Baked Beans | Yield "About 8 servings", which the 1896 book never gives | invented |
| Indian Pudding | ginger used in the method, missing from the list | ingredients |
| Strawberry Short Cake | 3 teaspoons baking powder where the original says 4 | invented |

They stay in: `tests/test_example_review_demo.py` fails if one is fixed or the
audit stops finding it. Undo your edits with `git checkout examples/`.

## In a container

The `Dockerfile` builds an image with the engine, Chromium, Ghostscript,
poppler, and the AI extra, for running `cookbook` on a machine where none of
them are installed. It has no entrypoint: run the command you need with the
book's folder mounted.

```bash
docker buildx build --platform linux/amd64 -t family-cookbook .
docker run --rm -v "$PWD/our-cookbook:/work/book" family-cookbook \
  cookbook press --book /work/book
```

`cookbook press` takes about 3 seconds a page on a laptop: the 30-page example
book takes about 83 seconds, and a book takes a few minutes for every 50 pages.
The work is mostly single-threaded, so 2 CPUs are enough.

## Troubleshooting

**Chromium will not start, or `playwright` says the browser is missing.** Run
`python -m playwright install chromium` with the virtual environment active. On
Linux, `python -m playwright install --with-deps chromium` also installs the
system libraries Chromium needs (it asks for your password).

**`gs` or `pdftoppm` not found.** Install Ghostscript (for `cookbook press` and
`cookbook export`) or poppler (for `cookbook ingest` on PDFs); see
[Requirements](#requirements).

**`no book/book.yaml in … or any folder above it`.** Run the command inside the
book's folder or a folder inside it, pass `--book PATH` with the book's folder,
or start a book with `cookbook init`.

**Lint reports `` placeholder text from `cookbook init` ``.** `cookbook init`
writes placeholders (marked `TODO`) for the pages only you can write.
Replace each line it names with your own words. `cookbook press` will not run
until they are gone.

**`cookbook check` fails: text runs past the edge of the page, or would print
below 10 pt.** A page holds more than fits at a readable size. The message
names the recipe on the page and how to fix it: shorten the recipe (trim it, or
move stories from its Notes into the original, `sources/recipe-original.md`),
or give it a two-page layout with a `layouts:` row in `book.yaml`
(`Recipe Spread` or `Two-Page Spread`; see
[LAYOUTS.md](docs/LAYOUTS.md#choosing-a-layout-yourself)). Two facing pages are
the most one recipe can take, so a recipe that still does not fit on the
Recipe Spread has to be shortened. `cookbook check --verbose` adds the
measurements behind each failure.

**The book has blank pages.** Chapter openers start on a right-hand page and
two-page recipes on a left-hand one, so a few blank pages fall between them. A
hardcover needs at least 24 pages, so a short book is padded with blank pages
at the back; the build summary says so.

**More than 800 pages.** That is the most a Lulu hardcover can hold; split the
book into volumes.

**A warning about the inside margin past 150 pages.** Longer books need a wider
margin at the binding than the engine's 0.75 inch. Open an
[issue](https://github.com/scanady/family-cookbook/issues) with your page count
before printing a book that long.

**`cookbook agent-files` fails on Windows.** It creates symbolic links, which
Windows only allows with Developer Mode turned on (Settings → System → For
developers) or from an administrator prompt.

## Glossary

| Term | Meaning |
|---|---|
| **Trim** | The finished page size after the printer cuts the paper: 8.5 × 11 in. |
| **Bleed** | An extra 0.125 in past the trim on every side, so a photo that runs off the page has no white sliver after cutting. Print pages are 8.75 × 11.25 in. |
| **Gutter** | The inside margin, at the binding. |
| **Recto / verso** | The right-hand (odd-numbered) page / the left-hand (even-numbered) page of an open book. |
| **Casewrap** | A hardcover whose printed cover is wrapped around the boards, as opposed to a cloth cover with a dust jacket. |
| **Spine** | The back edge of the bound book. Its width depends on the page count; `cookbook cover` sizes it. |
| **Slug** | An entry's folder name, lowercase with hyphens: `skillet-cornbread`. |
| **Entry** | One recipe or one prose page, each in its own folder. |
| **Layout (archetype)** | The arrangement of photo and text on an entry's page. There are seven ([LAYOUTS.md](docs/LAYOUTS.md)). |
| **Keepsake** | A card scan, family photo, or letter printed with an entry, listed in its `extras/extras.md`. |

## Getting help

Ask questions and report bugs in
[GitHub Issues](https://github.com/scanady/family-cookbook/issues).

## Contributing

Issues are welcome; pull requests are not accepted for now. See
[CONTRIBUTING.md](CONTRIBUTING.md). How the engine is organized is in
[AGENTS.md](AGENTS.md). To run the tests from a clone:

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE). You may use, change, and share the
engine for any noncommercial purpose, including making your own family's
cookbook and printing copies for your family. Commercial use needs a separate
license: contact the author through [GitHub](https://github.com/scanady).

The bundled Playfair Display and Source Sans 3 fonts are under the SIL Open
Font License ([`src/family_cookbook/fonts/`](src/family_cookbook/fonts/)).
