# Layout Catalog

The named page archetypes the engine's `render.py` draws (`RENDERERS`). Each recipe page uses exactly one. The engine assigns them automatically — content fit first, then a rotation that varies neighboring pages — and a `layouts:` row in `book/book.yaml` overrides the choice for one entry. Percentages are of page trim height (top = 0%) unless noted. All zones stay inside the safe margin except full-bleed backgrounds.

Every archetype names the **image zone** it reserves. That zone is the handoff contract with `design-visual-cookbook-image-generator`: the photo fills it while the rest of the page stays content-safe.

The engine draws no other layouts: there is no multi-image grid and no bespoke page. A `layouts:` row naming anything else fails `cookbook lint`.

## Selection Quick Reference

| Archetype | Images | Text density | Signature use |
|-----------|--------|--------------|---------------|
| Hero Full-Bleed | 1 strong | light–medium | Showpiece dish, short recipe |
| Half-Page Classic | 1 | light–heavy | The default workhorse; the photo takes the room the text leaves |
| Sidebar Portrait | 1 tall | medium | A glass or mug beside a medium recipe |
| Text-Only Framed | 0 | light–medium | No photo; strong family voice |
| Inset Original | 1 + scan | light–medium | Feature the transcribed original; assigned only by a `layouts:` row |
| Two-Page Spread | 1 full-page | one full page of text | A full-page photograph facing the whole recipe |
| Recipe Spread | 0–1 | more than one full page | One recipe composed across both facing pages |

**Readability floor:** no ingredient, direction, note, or prose line may print below 10 pt. The engine's `render.py` only auto-assigns a one-page archetype the recipe fits at full type — a band or hero whose photo keeps its minimum height beside the text (`photo_room()`), or a fixed layout within its `FULL_TYPE_LINES` budget; a recipe that fits none takes two facing pages — the Two-Page Spread when its whole recipe fits that layout's recipe leaf and its photo suits a full page, else the Recipe Spread. `cookbook check` fails the print build on any page whose recipe text `FIT_SCRIPT` zoomed below 10 pt.

**Photo size:** a band's or the hero's photo has no fixed height. It takes all the height the text leaves, within a range (band 3–6.75 in; hero 5–7.25 in), so a short recipe gets a big picture, a long one a smaller one, and no page ends in a stretch of empty paper below its text. There is no thin strip over a dense body: a recipe whose text would leave the photo less than the band's 3 in takes two pages.

**Photo fit:** a photo archetype must show the dish. The engine's `render.py` frames every photo around the dish it detects in it (tightening around a small dish, never below 300 ppi), and `photo_fit()` decides whether the frame qualifies — a band at the height the text leaves it. The food and its vessel are judged apart: like any food photograph, a frame may crop a bowl's side or a plate's edge, but never the food, and never through the subject's top — a glass's rim, a pint's head, a cake's crown. Hero Full-Bleed and the Two-Page Spread show the whole food; Half-Page Classic holds at least `BAND_FOOD_HELD` (55%) of the food's mass, so a short band may trim the outer edge of a deep dish but keeps its body. Sidebar Portrait takes only a narrow, standing subject (a glass, a mug) it shows whole across and that fills the column; such a subject keeps its whole silhouette, foot included, in any frame. A photo never decides a two-page layout: a short recipe whose photo suits no one-page frame takes the band or hero showing the most food, and `cookbook fit` flags the photo for regeneration.

Automatic assignment already avoids repeating the previous page's exact look. Override with a `layouts:` row only when a page needs a different archetype than the engine chose — for example, Inset Original, which is never auto-assigned.

---

## Hero Full-Bleed

One commanding photograph carries the page; the recipe rides in a compact panel.

- **When:** a single strong finished-dish image and a light-to-medium recipe. Reserve for showpiece dishes; do not overuse, or the book loses its rhythm.
- **Image zone:** full-bleed across the top of the page box, through the bleed on three edges, down to the text panel: the photo takes all the height the panel leaves, 5–7.25 in of the 11.25 in page, so the whole crop is visible and the panel is as tall as its text.
- **Text:** title and attribution in a solid panel below the photo with an accent rule at the seam; ingredients and directions in two columns.
- **Reserved content-safe region:** none in the photo; the panel is opaque paper.
- **Overflow:** none; if the recipe would leave the photo under 5 in, choose a different archetype.

## Half-Page Classic

The everyday cookbook page: photo on one half, recipe on the other.

- **When:** one finished-dish image and any text that leaves the photo at least 3 in. Default when nothing special applies — it is also the page for long recipes, which simply get a shorter photo.
- **Image zone:** a band across the text column above the title (upper), between the header and the recipe (centered), or at the foot of the page (lower). Rotate the placement across the book — this is the easiest lever for variety. The band takes the height the text leaves, 3–6.75 in; the browser frames the canonical photo in it around the food once its height is known (no pre-cut crop).
- **Text:** title/attribution/metadata plus ingredients and directions in two columns, at their natural height; the band, not the text, absorbs the page's spare height.
- **Reserved content-safe region:** the text block, above or below the band.
- **Overflow:** a recipe whose text would leave less than 3 in takes a two-page layout.

## Sidebar Portrait

A tall image column beside a text column.

- **When:** a genuinely narrow, tall subject — a glass, a mug — that the column shows whole across its width and fills top to bottom, with a recipe long enough to fill at least half the text column beside it (`SIDEBAR_MIN_LINES`); shorter recipes take a band or the hero. A wide dish (a casserole, a bowl, a pie) never qualifies: the column could only slice through its middle above a column of backdrop. In practice that means drinks — a mulled wine, a cocktail.
- **Image zone:** a vertical column, left or right, about 40–48% of page width and 70–90% of height, framed with a thin keyline and inside the safe margin.
- **Text:** title spans full width at top; the opposite column holds ingredients above directions.
- **Reserved content-safe region:** the text column and the header band.
- **Overflow:** choose a two-page layout.

## Text-Only Framed

A purely typographic page — no photograph.

- **When:** no image exists and none is planned, or the recipe's charm is its voice (an anecdote, a phone number, a one-liner). Lean into type.
- **Image zone:** none. Instead reserve a decorative element — a category-accent rule, a drop-cap title, or a pull quote lifted verbatim from the directions.
- **Text:** generous margins, a display title, and a single elegant column or a light two-column split. Feature one pull quote in the accent color.
- **Reserved content-safe region:** the whole page is text; use whitespace as the design.
- **Overflow:** a recipe too long for the page takes a two-page layout. A prose page too long for one leaf at full size continues on the next leaf, in the same frame under a running head "{Title}, continued"; a paragraph splits there only at a line boundary, with at least two lines on each side.

## Inset Original

Pairs the clean recipe with its transcribed original — a card, a clipping, a printed page — as a keepsake, under the label "From the original".

- **When:** an `-original.md` scan exists and is worth featuring, and text density is light-to-medium. Never auto-assigned: name it in a `layouts:` row.
- **Image zone:** the finished-dish photo in a half or sidebar zone (per fit), plus a small inset panel (styled like an aged card or a tinted box) holding an excerpt or full text of the original.
- **Text:** clean recipe as primary; the inset is clearly secondary, smaller type, accent-tinted background.
- **Reserved content-safe region:** primary recipe column plus the inset panel bounds.
- **Overflow:** shrink the original to an excerpt with a "View the original recipe" link rather than spilling to page 2.

## Two-Page Spread

Two facing leaves for one recipe: the photograph gets a whole page, the recipe gets the other. The classic cookbook spread — the dish faces its recipe, and nothing spills.

- **When:** the recipe fits no one-page archetype at full type, has a photograph, and its whole recipe fits one full text page at 10 pt or more. Auto-assigned: `assign_section()` picks it when the recipe's `_body_lines` estimate is within the `"Two-Page Spread"` budget in `FULL_TYPE_LINES` (calibrated on this layout's recipe leaf in the print geometry, like the one-page budgets). Also available from `book.yaml` for a photograph that earns a full page.
- **Image zone:** the entire verso — full-bleed on all four edges, no folio, no caption. The photo is the page (`-spread` crop, 8.75 × 11.25 in). Direct the generator to compose for a full 8:11 portrait page, not a half-page zone; a landscape shot padded onto a portrait canvas leaves half the page empty.
- **Text:** the facing recto carries the full header and the recipe at 10.5 pt in two columns, top-aligned: ingredients (subheads included) in a narrow column of about 38% of the measure, directions in the wide one with the notes following them, and any spare paper at the foot. Only when the page cannot hold that single ingredient column at full size does `splitIngredients()` in `FIT_SCRIPT` try a wider ingredient column flowed in two sub-columns (`two-col--split`), keeping it if it needs less room — decided by measurement, not by ingredient count. Three or fewer ingredients stack above the directions in one column instead.
- **Reserved content-safe region:** all of the recto. The verso reserves nothing.
- **Pagination:** the photo leaf is forced onto a verso by `insert_recto_blanks()`, so the pair always faces: the next ordinary recipe of the same chapter is lifted in front of it, or a blank fills the slot. The screen draft paginates the same way and shows the pair side by side. The contents, index, and contributors list the recipe once, at the recto's folio; extras always go on a keepsake page after the recto. Without a photograph on disk the layout collapses to its recipe page alone.
- **Overflow:** if the recipe overflows the recto, use the Recipe Spread.

## Recipe Spread

One recipe longer than a full page of text, composed across both facing pages as a single design rather than a page that spills onto the next.

- **When:** the recipe fits no one-page archetype and is over the Two-Page Spread budget, or has no photograph to face it. Auto-assigned; a chili or stew with dozens of ingredients and a long method is the typical case.
- **Grid:** the spread is one four-column grid, two columns a page, on the same top margin and column measure on both pages. The title block (title, attribution, accent rule, metadata) heads the verso; the recto carries a small running head, "{Title}, continued", in the accent label style over a hairline.
- **Text:** ingredients, then directions, then notes, at 10.5 pt, flowed column by column across the spread: the verso's two columns fill first, and the rest is balanced across the recto's two so it ends level. Ingredients finish before directions start. A step, ingredient, or note is never split, and a section heading or ingredient subhead always travels with the item beneath it; a continued list of steps keeps its numbering. The flow is measured in the browser by `flow()` in `FIT_SCRIPT`, which runs before the zoom pass, not estimated in Python.
- **Image zone:** the photograph absorbs whatever space the flow leaves — the full width of the recto's text area below its columns, at least 2.5 in tall. When the recto has no text left for it (the whole recipe fits the verso), the photo fills the recto's text area and the running head is dropped. When less than 2.5 in is left, the photo becomes a 2.5 in band under the verso's title block and the text is flowed again around it. It uses the canonical image (no derived crop — its height varies with the text), trimmed in place by `object-fit` and the recipe's `Image position`; direct the generator to keep the subject centred so any crop from a wide band to a full page holds it.
- **Reserved content-safe region:** the verso below the title block and the recto above the photo.
- **Pagination:** as the Two-Page Spread — the verso always lands on an even page, in print and on screen. The contents, index, and contributors list the recipe once, at the verso's folio; extras always go on a keepsake page after the recto.
- **Overflow:** if the text outruns all four columns, `FIT_SCRIPT` shrinks the recto and `cookbook check` fails it below 10 pt — cut content; there is no page 3.

