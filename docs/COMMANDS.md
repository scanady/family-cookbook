# Commands

Everything the `cookbook` command does, for when the [README](../README.md)'s
five commands are not enough. If you installed with `install.sh`, run each one as
`./cookbook` from the book's folder.

Run any command from the book's folder or a folder inside it, or pass
`--book PATH`. `cookbook COMMAND -h` lists a command's options.

- [Every command](#every-command)
- [AI: what it does without a key](#ai-what-it-does-without-a-key)
- [A book's folder](#a-books-folder)
- [Install by hand](#install-by-hand)
- [Upgrade](#upgrade)
- [In a container](#in-a-container)
- [The example book](#the-example-book)

## Every command

**Start**

| Command | What it does |
|---|---|
| `cookbook init [--categories a,b] [--sections x,y] [--title T] [--subtitle S] [--edition E] [--dry-run]` | Start a new book in the current folder (or `--book PATH`). `--categories` are the recipe chapters, in order (default `breakfast,mains,sides,desserts`); `--sections` are chapters of writing, such as family stories. Writes `book/book.yaml`, a folder per chapter, placeholder pages, `.gitignore`, `.env` for the AI key, and the guides AI coding assistants follow. Never overwrites a file. |
| `cookbook doctor` | Check that this computer can make the book: Chromium, Ghostscript, poppler, the AI key, and the book folder. Each failing check prints the command that fixes it. Exits 1 if Chromium or Ghostscript is missing. |

**Write and review**

| Command | What it does |
|---|---|
| `cookbook ingest FILE... [--pages P] [--chapter C] [--cook NAME] [--title T] [--model M] [--dry-run]` | Type up photos, scans, or PDFs of recipes with an AI model. `--chapter` files every recipe in one chapter; `--cook` credits every recipe to one person. Without an AI key, files the pages as one recipe to type up by hand; `--title` names it. |
| `cookbook photo SLUG... [--attempts N] [--new-prompt] [--prompt-only] [--model M] [--image-model M]` | Make a photo of each recipe's finished dish with an AI model. `--prompt-only` writes the prompt to edit first. Without an AI key, warns and makes nothing. |
| `cookbook studio [--port N] [--no-open]` | Work on the whole book in your browser (port 8770). |
| `cookbook review [--all] [--port N] [--no-open] [--report]` | Only the studio's recipe review, on its own (port 8765). Approvals and time spent go to `book/sources/review-log.jsonl`; `--report` prints the average time per recipe. |

**Check**

| Command | What it does |
|---|---|
| `cookbook lint [--errors] [--quiet]` | Find mistakes in the book's files: missing sections, broken links, leftover `TODO` text. Exits 1 on errors. |
| `cookbook audit [--check]` | Read every recipe for content mistakes and write `draft/book-report.html`, errors first, with links to the pages. It checks for a recipe cut off mid-sentence; a cook time or temperature the directions do not support; a yield, time, or amount the original never states; an ingredient the method uses but the list leaves out; a line of the original left out; and a phone number, email, or street address in printed text. `--check` also runs `cookbook check`. |
| `cookbook check [HTML] [--verbose]` | Find printed pages where text runs off the page or prints smaller than 10 pt, in `draft/cookbook-print.html`. Exits 1 if there are any. |

**Print**

| Command | What it does |
|---|---|
| `cookbook press` | Make the two PDFs to upload: runs lint, fit, build --print, check, export interior, cover, and export cover in turn, and stops at the first failure. About 3 seconds a page. |
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

## AI: what it does without a key

Two commands use AI: `ingest` and `photo`. They read a key from the book's
`.env` file, which `cookbook init` writes with both lines empty:

- `GEMINI_API_KEY`: a key from [Google AI Studio](https://aistudio.google.com/apikey),
  for Google's Gemini API.
- `OPENROUTER_API_KEY`: a key from [OpenRouter](https://openrouter.ai/keys). It
  reaches the same Gemini models (`gemini-3.8-flash` becomes
  `google/gemini-3.8-flash`), paid from prepaid credits. `--model` and
  `--image-model` also take any OpenRouter model id, such as `vendor/model`;
  the prompts were written and checked against Gemini, so check another
  model's work closely. OpenRouter does not read HEIC photos: save them as JPEG.

With both keys, Gemini is used. A key already set in your shell wins over
`.env`. Git never commits `.env`.

With no key, both commands say so and carry on without AI:

- **`ingest`** makes one recipe folder from the pages you give it. It keeps the
  pages as the original and writes a `recipe.md` whose ingredients and
  directions say `TODO`. Type the recipe up beside the card in the studio's
  Recipes tab. Lint reports each `TODO` line until you do, so `press` cannot
  print it unfinished.
- **`photo`** makes no photo. The recipe prints without one, or you add your
  own ([RECIPE-FORMAT.md](RECIPE-FORMAT.md)).

**Cost.** Each AI command adds a line per recipe to `book/sources/ai-log.jsonl`
with the tokens used and the cost in US dollars. At the October 2026 prices in
the engine's price table, each picture the default image model draws costs
about $0.24, so one dish photo costs $0.24–$0.72 for one to three attempts,
plus the text model's calls that write the prompt and check each picture.

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
  cookbook                             the launcher install.sh writes
  .venv/                               the engine, installed; not committed
  index.md                             written by cookbook index
  .env                                 your AI key; not committed
  .gitignore
  .agents/skills/                      guides for AI coding assistants (cookbook agent-files)
  .claude/skills, .github/skills       links to .agents/skills
  .github/instructions/                the recipe and page format rules, for AI coding assistants
```

A **slug** is an entry's folder name, such as `skillet-cornbread`. The guides
let an AI coding assistant (Claude Code, GitHub Copilot, and others) transcribe
recipes, add keepsakes, and run the checks for you. The `cookbook` command
works without them.

Keep the book's folder in git to keep its history; the `.gitignore` leaves out
the generated files and your key.

## Install by hand

`install.sh` runs these steps. To run them yourself, you need Python 3.11 or
newer and Ghostscript (`sudo apt install ghostscript` or
`brew install ghostscript`):

```bash
mkdir our-cookbook && cd our-cookbook
python3 -m venv .venv
. .venv/bin/activate
pip install "git+https://github.com/scanady/family-cookbook@v1.2.0"
python -m playwright install chromium
cookbook init --title "Our Family Cookbook" --subtitle "The Smith Family"
cookbook doctor
```

Run `. .venv/bin/activate` again in each new terminal before using `cookbook`.
To read recipes from PDF files, also install poppler (`sudo apt install
poppler-utils` or `brew install poppler`).

## Upgrade

Run `install.sh` again in the book's folder, with the new version:

```bash
curl -fsSL https://raw.githubusercontent.com/scanady/family-cookbook/main/install.sh | bash -s -- .
```

It upgrades the engine and the AI assistants' guides, and leaves `book/` alone.
By hand: run the `pip install` line with the new tag, then
`cookbook agent-files --update`.

## In a container

The `Dockerfile` builds an image with the engine, Chromium, Ghostscript, and
poppler, for running `cookbook` on a machine where none of them are installed.
It has no entrypoint: run the command you need with the book's folder mounted.

```bash
docker buildx build --platform linux/amd64 -t family-cookbook .
docker run --rm -v "$PWD/our-cookbook:/work/book" family-cookbook \
  cookbook press --book /work/book
```

`cookbook press` takes about 3 seconds a page on a laptop: the 30-page example
book takes about 83 seconds. The work is mostly single-threaded, so 2 CPUs are
enough.

## The example book

The example book is in this repository, not in the installed package. From a
clone:

```bash
git clone https://github.com/scanady/family-cookbook
cd family-cookbook
cookbook build --book examples/fannie-farmer-1896     # draft/cookbook-draft.html
cookbook audit --book examples/fannie-farmer-1896     # draft/book-report.html
cookbook studio --book examples/fannie-farmer-1896    # fix them beside the original
```

The example has four mistakes on purpose, the kind an editor fixes in review,
so the report and the studio have something real to show:

| Recipe | Mistake | Check |
|---|---|---|
| Fish Chowder | Cook time 20 minutes, the first time in the text; the stages add to 45 | cook time |
| Boston Baked Beans | Yield "About 8 servings", which the 1896 book never gives | invented |
| Indian Pudding | ginger used in the method, missing from the list | ingredients |
| Strawberry Short Cake | 3 teaspoons baking powder where the original says 4 | invented |

They stay in: `tests/test_example_review_demo.py` fails if one is fixed or the
audit stops finding it. Undo your edits with `git checkout examples/`.
