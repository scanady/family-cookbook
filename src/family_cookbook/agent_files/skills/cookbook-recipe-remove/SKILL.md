---
name: cookbook-recipe-remove
description: 'Remove a recipe or page from the family cookbook completely — its folder, its photo, its curated layout row, its index entry — and confirm the book still renders and paginates correctly afterwards. Use when asked to "remove this recipe", "delete a recipe from the cookbook", "take this page out of the book", "pull the recipe we duplicated", or "retire an entry".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: cookbook-recipe-ingest, cookbook-lint
---

# Cookbook Entry Removal

Take an entry out of the book without leaving anything behind. Deleting the folder is the easy part and the smallest part — a removed recipe leaves references in the layout manifest, the index, and possibly its chapter's `pinned` list, and it shifts the pagination of every page after it.

## Role Definition

You are performing a careful retraction on a document that is about to be printed. Half-removed content is worse than content left in: a stale manifest row is invisible until someone wonders why a curated layout stopped applying, and a broken index link is visible to every reader on GitHub.

## When To Use

Use this when an entry should leave the book: a duplicate, something added by mistake, a recipe a family member asked to withdraw, or a page that no longer fits.

Do not use it to edit an entry that is staying (just edit the file), or to move an entry between categories — that is a rename, and Step 3 below is the part that matters there.

## Before You Delete Anything

**Confirm the target with the user, by title and path**, and confirm they mean removal rather than an edit. Deletion of family material is not obviously reversible to someone who is not thinking about git, and the photo may be the only copy of an image that cost money to generate.

If the entry has a photograph, say so explicitly before deleting — `images/{slug}.jpg` is a real asset, and it is committed history rather than something regenerable for free.

## Workflow

### Step 1: Find every reference

```bash
grep -rn "{slug}" --exclude-dir=.git --exclude-dir=draft .
```

Run this before deleting, and keep the output. It is your checklist — the folder itself, plus every other place the slug appears.

### Step 2: Remove the entry folder

```bash
git rm -r book/recipes/{chapter}/{slug}   # or book/sections/{section}/{slug}
```

Use `git rm` rather than a plain delete so the removal is staged and the photo actually leaves the working tree.

### Step 3: Clear the curated layout row

Open `book/book.yaml` and delete the entry's block from the `layouts:` list if it has one. Most entries are auto-assigned and have none; curated ones do.

A stale row is not harmless. The engine's `render.py` matches rows by `(category, slug)` and silently ignores ones that match nothing, so the book keeps building and the mistake keeps sitting there. `cookbook lint` catches this — which is why Step 6 is not optional.

Also delete the entry's layout note if the row's optional `spec:` pointed at one (`prompts/{slug}-layout.md` inside the folder you just removed — usually gone already). Most entries have none; only `cookbook lint` reads that path.

### Step 4: Clear the ordering pin, if there is one

A chapter's `pinned` list in `book/book.yaml` holds named slugs at the front of that chapter. If the removed slug is listed there, delete it. A dead pin is silently ignored at build time; `cookbook lint` warns about it.

### Step 5: Check whether the section is now empty

If that was the last entry in its chapter, the chapter's section divider now introduces nothing — `cookbook lint` warns. Decide with the user whether to remove its divider message at `book/sections/{name}/page.md` as well, and whether the chapter should come out of the `chapters:` list in `book/book.yaml`.

### Step 6: Verify

```bash
cookbook lint                    # must be clean — catches stale manifest rows
cookbook index                   # regenerate index.md
cookbook build                   # full rebuild; note the new page count
```

Compare the page count against what it was before. It should fall — but by an amount you can explain. Section dividers are forced onto right-hand pages and the book is padded to an even total, so removing one page can change the count by two, or by nothing at all. If the count moves in a way that does not make sense, a blank leaf was inserted or dropped somewhere; open the draft and find where.

Finally, re-run the grep from Step 1. It should return nothing.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Curated layout rows | `book/book.yaml` | Clearing the entry's row, if it has one (Step 3) |
| Ordering pins and chapter list | `book/book.yaml` | Checking the chapter's `pinned` list, and when a chapter is left empty (Steps 4–5) |
| Stale-reference checks | `cookbook lint` | Verifying nothing was left behind (Step 6) |
| Adding an entry back | `cookbook-recipe-ingest` | The user meant a move or a rewrite rather than a removal |

## Constraints

### MUST DO

- Confirm the target entry by title and path, and confirm removal is meant rather than an edit, before deleting anything.
- Say explicitly when the entry has a photograph, before it is deleted.
- Grep for the slug before deleting and keep the output as the removal checklist.
- Use `git rm -r` so the removal is staged and the assets leave the working tree.
- Delete the entry's layout row and any `pinned:` entry naming it.
- Raise the empty-section question when the last entry of a category is removed.
- Run `cookbook lint`, `cookbook index`, and a full rebuild afterwards.
- Re-run the original grep and confirm it returns nothing.
- Explain the page-count change, including any blank leaf inserted or dropped.

### MUST NOT DO

- Delete family content without explicit confirmation from the user.
- Remove the folder and stop — a stale manifest row or ordering pin fails silently.
- Remove a section divider or a chapter from the `chapters:` list in `book/book.yaml` without asking.
- Treat a clean build as proof of a clean removal; the renderer ignores dangling references by design.
- Accept an unexplained page-count change.

## Knowledge Reference

Entry retraction, staged deletion, dangling reference, stale layout row, curated vs. auto assignment, category ordering pin, section divider, recto pagination, blank leaf insertion, even page-count padding, slug grep sweep, generated index refresh, empty section cleanup, book structure list

## Done When

- The entry folder is gone, staged via `git rm`.
- No manifest row, ordering pin, or divider refers to it.
- `grep -rn "{slug}"` returns nothing outside `.git` and `draft/`.
- `cookbook lint` is clean.
- `index.md` is regenerated and the book rebuilds, with a page-count change you can explain.
