---
description: "Use when creating or editing cookbook front matter, back matter, section dividers, family notes, jokes, household tips, or other non-recipe pages."
applyTo: ["book/sections/**"]
---
# Non-Recipe Pages

Non-recipe entries live in one of two bases, by role. Both use the same `page.md` format; they differ in whether they are a chapter of the book or furniture around it.

**Prose chapters** — `book/sections/{chapter}/{slug}/`. Family notes, jokes, household tips: content that is a chapter the way Desserts is a chapter. It takes a place in the `chapters:` list in `book/book.yaml`, with a `label`, an `accent`, and an opening page.

**Matter pages** — `book/sections/matter-dedication/page.md`, `book/sections/matter-closing-message/page.md`. Each is its own single-page chapter, carrying `divider: false` and sitting at its place in the `chapters:` list. A dedication is a chapter without a divider before the first food chapter.

A single-page chapter keeps its `page.md` at the **chapter root** — no `{slug}/` level, since that level exists to separate multiple entries. A chapter is either one page or a group of entries, never both.

Either way the entry folder is:

- `page.md`: clean source of truth
- `sources/page-original.md`: optional verbatim transcription
- `extras/`: optional keepsakes, printed only when listed in `extras/extras.md` (`![Caption](file.jpg)` lines) — see the `cookbook-extras` skill

A chapter's own keepsakes go in `book/sections/{chapter}/extras/` and print with its opening page, or on a keepsake page after it when the page has no room. Never create an empty `sources/` or `extras/` folder.

Put prose under `book/recipes/` and it lands in a base reserved for food. `cookbook lint` treats that as an error, along with a name present in both `book/recipes/` and `book/sections/`, which would silently drop half the group.

Do not force recipe metadata, Ingredients, or Directions onto these pages. Match the source's natural structure with prose paragraphs or simple lists; preserve meaningful paragraph and blank-line breaks instead of making every source line a paragraph.

`book/sections/{chapter}/page.md` is the chapter's **own** page — the one belonging to the chapter rather than to any entry. One file name doing one job: `divider: true` renders it as the section opener before the entries; `divider: false` renders it as a page in the flow, which is what a dedication or a closing message is.

**A chapter has an opening page because `book.yaml` says so**, not because the file exists. The file is optional — a section opening with just its chapter name is fine. An empty file is an error; delete it instead.

**A chapter page has no H1.** Its heading is the chapter's `label`, the same string the table of contents prints; a heading here would be a second copy free to drift. Write the prose and nothing else. Entries, by contrast, do carry an H1 — an entry's title belongs to it and is duplicated nowhere.

Entry order within a chapter is alphabetical unless the chapter carries a `pinned:` list in `book/book.yaml` — available to any chapter, not just front and back matter.

`pinned` holds those entries at the **front** of the chapter, in the order given; everything unpinned follows alphabetically after them. Pinning some and not others is normal and expected.

What `pinned` **cannot** do is hold an entry at the **back**. Single-page chapters avoid the problem entirely — each matter page is its own chapter, so its position is its place in the `chapters:` list. Reach for `pinned` only inside a chapter that genuinely groups several entries.

**Four pages are generated, never authored: the title page, the contents, the contributors, and the index.** Each is a `kind: generated` chapter in `book/book.yaml` with no folder; its place in the `chapters:` list is where it prints and its `label` is its heading. A generated page left out of the list doesn't print — the index is optional and off by default, since the contents and contributors already list every dish and cook; uncomment its block to print it. The title page renders from `book.title`, `book.subtitle`, and `book.edition`; the contents from the page order; the contributors (every cook, by surname, with their dishes and pages) and the index (dish titles and cooks, A–Z) from each entry's title and attribution line. The contents, contributors, and index run onto as many pages as they need. Creating any of them as markdown does not override the generated page — `cookbook lint` rejects the folder.

**The attribution line feeds the contributors and the index**, so write joint credits so they split: `Ann Lee and Bob Lee`, `Ruth and Tom Baker` (the surname is shared), `Ruth Baker/Jane Baker`. `(submitted by …)` after a name credits the cook only; the submitter is not listed for that dish.
