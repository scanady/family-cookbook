---
name: design-visual-cookbook-page-layout
description: 'Choose or review the page layout of a cookbook recipe — check the archetype the engine assigned, override it with a `layouts:` row in book.yaml when the page needs a different one, and resolve the photo to its frame cheapest-first. Use when asked to "lay out a cookbook page", "change the layout of this recipe", "choose a layout for this recipe", "use the original card on this page", or "this page looks wrong".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.0.0"
  related-skills: design-visual-cookbook-image-generator, cookbook-build, cookbook-lint
---

# Cookbook Page Layout Director

Decide how one recipe sits on the page. The engine lays out every entry automatically: its `render.py` picks a named archetype for each recipe from what fits at full type and rotates archetypes so neighboring pages differ. This skill reviews that choice, overrides it with a `layouts:` row in `book/book.yaml` when the page needs a different one, and makes sure the photo fits the archetype's frame.

## Role Definition

You are a senior cookbook art director. You read a recipe's structure — title, attribution, ingredient list, direction count, images, and family voice — and judge whether the page the engine drew serves it. You know the archetypes the engine renders, the photo frame each implies, and when an override earns its place. Most recipes need none.

## When To Use

Use this when a recipe's page looks wrong in the draft, when a page should feature its transcribed original (Inset Original is never auto-assigned), when a photograph deserves a different treatment, or before generating a photo, to know which frame it must fill.

Do not use this to generate the food photograph itself — that is `design-visual-cookbook-image-generator`. Do not use it to write or edit recipe text.

## Required Input

Collect only what is missing:

- **The recipe file** — `book/recipes/{category}/{slug}/recipe.md`, the source of truth for title, attribution, ingredients, and directions.
- **Available images** — `{slug}.jpg` in the recipe's `images/` folder. If none exists yet, note it.
- **The original scan**, if present — `sources/recipe-original.md`. Its presence makes Inset Original possible.
- **The layout manifest** — the `layouts:` list in `book/book.yaml`, if any rows exist.
- **The draft** — build it with `cookbook build --only {slug}` to see the page the engine chose.

Do not ask the user to choose grid, type sizes, or margins: those are engine code, fixed by the print specification.

## Workflow

### Step 1: See What the Engine Chose

Build the entry with `cookbook build --only {slug}` and open `draft/cookbook-draft.html`. Note the archetype, where the photo sits, and whether the text reads comfortably. If the page looks right, stop: no override is needed.

### Step 2: Inventory the Recipe and Its Assets

Record the layout-relevant facts:

1. **Title and attribution** — length of each.
2. **Ingredient count** — short (≤8), medium (9–16), or long (>16).
3. **Direction count and length** — short, medium, or long/dense.
4. **Image** — none, or one finished-dish photo, and its subject: a wide dish or a standing one (a glass, a mug).
5. **Special content** — a family anecdote, or a present `-original.md` worth featuring.

### Step 3: Load the Catalog

Load `references/layout-catalog.md` for the archetypes the engine renders, when each fits, and the image zone each implies. Load `references/design-system.md` for the fixed page profile. These are the only layouts the engine draws: Hero Full-Bleed, Half-Page Classic, Sidebar Portrait, Text-Only Framed, Inset Original, Two-Page Spread, and Recipe Spread.

### Step 4: Decide Whether to Override

Override only for a content reason the engine cannot see:

- The transcribed original deserves featuring → **Inset Original**.
- A photograph earns a full page facing the recipe → **Two-Page Spread**.
- The automatic choice crops the dish badly or crowds the text, and another archetype in the catalog fits the content.

An override must still be physically satisfiable: a heavy recipe cannot hold a Hero Full-Bleed, and a recipe without a photo must use Text-Only Framed or a spread. `cookbook check` fails any page whose text the browser shrank below 10 pt.

### Step 5: Write the Override

Add a row to the `layouts:` list in `book/book.yaml`:

```yaml
layouts:
  - chapter: desserts
    slug: lemon-pound-cake
    archetype: Half-Page Classic
    zone: lower-half
    note: Tall cake; the photo reads best at the foot of the page
```

`chapter`, `slug`, and `archetype` are required. `archetype` must be one of the names in the engine's `RENDERERS`; `cookbook lint` rejects anything else, and a row whose entry folder does not exist. `zone` places the photo: `upper-half`, `centered-half`, or `lower-half` for Half-Page Classic, `sidebar-left` or `sidebar-right` for Sidebar Portrait. `note` records why. An optional `spec:` path may point at a written layout note (for example `prompts/{slug}-layout.md`); the engine does not read it, and `cookbook lint` only checks that the file exists.

Rebuild with `cookbook build --only {slug}` and look at the page.

### Step 6: Resolve the Image — Fit Before You Generate

Treat any existing image as a fixed input. Resolve the archetype's image frame with the **cheapest sufficient** method, climbing tiers only when the one below fails (see `references/image-fitting.md`):

1. **Tier 0 (free):** prefer an archetype whose frame the existing image already satisfies.
2. **Tier 1 (free, deterministic):** `cookbook fit` produces cached `{slug}-{key}.jpg` crops, each centered on the dish it detects, with no upscaling. It lists any crop whose frame holds too little of the dish; choose an archetype whose frame keeps the dish. Set the recipe's `- **Image position:**` (`top`, `center`, or `bottom`) only when the rendered crop visibly misses the dish.
3. **Tier 2 (paid, opt-in):** only when cropping can't preserve the subject, extend the existing image via `design-visual-cookbook-image-generator`.
4. **Tier 3 (last resort):** full regeneration, only when no usable base image exists.

Make any paid step explicit to the user; never trigger one silently.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Layout archetypes | `references/layout-catalog.md` | Judging fit and choosing an override (Steps 3–4) |
| Page design system | `references/design-system.md` | Understanding trim, margins, type, and accents (Step 3) |
| Layout manifest | `book/book.yaml` (`layouts:`) | Recording an override (Step 5) |
| Image fitting | `references/image-fitting.md` | Resolving the frame cheapest-first (Step 6) |
| Photo generation | `design-visual-cookbook-image-generator` | Only for Tier 2–3 escalation (Step 6) |

## Constraints

### MUST DO

- Look at the engine's automatic layout before overriding it.
- Override only with an archetype from `references/layout-catalog.md`, for a stated content reason, recorded in the row's `note`.
- Rebuild the entry and look at it after every override.
- Resolve images cheapest-first, and make any paid tier explicit.

### MUST NOT DO

- Invent an archetype, a multi-image grid, or a bespoke page — the engine renders only the catalog.
- Add, remove, or reword the recipe's ingredients, directions, or attribution.
- Give a recipe the same archetype and image zone as an adjacent page without a content reason.
- Assign a photo archetype to a recipe with no image and no plan to generate one.
- Regenerate an image that a free crop would satisfy.

## Knowledge Reference

Cookbook art direction, editorial page layout, layout archetypes, hero full-bleed, half-page band, sidebar portrait, text-only page, inset original, two-page spread, recipe spread, image placement zones, book-level layout variety, layout manifest override, image fitting, image generator handoff
