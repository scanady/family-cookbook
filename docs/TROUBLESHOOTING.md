# Troubleshooting

Start with `cookbook doctor` (`./cookbook doctor` if you used an installer): it
checks Chromium, Ghostscript, poppler, the AI key, and the book folder, and
prints the command that fixes each one missing.

**Chromium will not start, or `playwright` says the browser is missing.** Run
the fix `cookbook doctor` prints. On Linux it installs the system libraries
Chromium needs too, and asks for your password.

**Ghostscript or `pdftoppm` not found.** Install Ghostscript (for
`cookbook press`) or poppler (for `cookbook ingest` on PDFs): `sudo apt install
ghostscript poppler-utils` or `brew install ghostscript poppler`. On Windows,
run `install.ps1` again for Ghostscript (or use the installer from
[ghostscript.com](https://ghostscript.com/releases/gsdnld.html)), and
`winget install -e --id oschwartz10612.Poppler` for poppler.

**Windows: `running scripts is disabled on this system`.** This shows up when
running a downloaded `.ps1` file. Use the `irm … | iex` line from the README
instead, which PowerShell allows, or run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

**`AI is off: no AI key`.** Paste a Gemini key from
[Google AI Studio](https://aistudio.google.com/apikey) after `GEMINI_API_KEY=`,
or an OpenRouter key from [openrouter.ai/keys](https://openrouter.ai/keys) after
`OPENROUTER_API_KEY=`, in the `.env` file in the book's folder. Until then,
`ingest` files the pages for you to type up and `photo` makes nothing; see
[COMMANDS.md](COMMANDS.md#ai-what-it-does-without-a-key).

**`OpenRouter has no credits left on this key`.** Add credits at
[openrouter.ai/settings/credits](https://openrouter.ai/settings/credits), then
run the command again.

**`no book/book.yaml in … or any folder above it`.** Run the command inside the
book's folder or a folder inside it, pass `--book PATH` with the book's folder,
or start a book with `cookbook init`.

**Lint reports `placeholder text`.** `cookbook init` writes `TODO` lines for the
pages only you can write: the dedication, each chapter's opening message, the
closing message, the back cover, and the subtitle in `book/book.yaml`.
`cookbook ingest` without AI writes them where the recipe still needs typing.
Replace each line lint names with your own words. `cookbook press` will not run
until they are gone.

**`cookbook check` fails: text runs past the edge of the page, or would print
below 10 pt.** A page holds more than fits at a readable size. The message
names the recipe on the page and how to fix it: shorten the recipe (trim it, or
move stories from its Notes into the original, `sources/recipe-original.md`),
or give it a two-page layout with a `layouts:` row in `book.yaml`
(`Recipe Spread` or `Two-Page Spread`; see
[LAYOUTS.md](LAYOUTS.md#choosing-a-layout-yourself)). Two facing pages are the
most one recipe can take, so a recipe that still does not fit on the Recipe
Spread has to be shortened. `cookbook check --verbose` adds the measurements
behind each failure.

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

**`.claude/skills` and `.github/skills` are folders, not links, on Windows.**
Windows allows symbolic links only in Developer Mode, so the engine copies
`.agents/skills` there instead; `cookbook agent-files --update` refreshes the
copies.

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
| **Layout (archetype)** | The arrangement of photo and text on an entry's page. There are seven ([LAYOUTS.md](LAYOUTS.md)). |
| **Keepsake** | A card scan, family photo, or letter printed with an entry, listed in its `extras/extras.md`. |
