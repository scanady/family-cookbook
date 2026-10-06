# Cookbook Page Design System

The fixed visual language of every page the engine renders. Trim, margins, grid, fonts, and type hierarchy are engine code, set to meet the print specification; a book chooses only its chapter accents (in `book/book.yaml`).

## Page Profile

| Property | Value |
|----------|-------|
| Trim size | 8 × 11 in portrait |
| Bleed | 0.125 in on all four edges (full canvas 8.25 × 11.25 in) |
| Text margin | 0.75 in from trim at the top and outer edge, 0.875 in at the bottom; the folio sits 0.5 in above the trim (Lulu's safety line), in clear paper below the text |
| Gutter (binding) margin | 0.75 in on the inner edge (covers Lulu's gutter minimum up to 150 printed pages; past that Lulu needs 1 in) |
| Resolution | 300 PPI — trim 2400 × 3300 px, full-bleed canvas 2475 × 3375 px |
| Color | Warm neutral paper base; accents applied sparingly |

Keep all critical text and meaningful image detail inside the text margin. Only backgrounds and full-bleed photos extend into the bleed. Never place text or key detail across the gutter.

## Grid

- **Columns:** 6-column modular grid across the live area (inside safe margins), 0.1667 in column gutters.
- **Common spans:** single text column = 6 cols; two-column recipe = 2 cols (ingredients) + 4 cols (directions) or 3 + 3; sidebar image ≈ 3 cols.
- **Spread grid:** a recipe too long for one page is designed as the open spread, not as a page and its overflow. The Recipe Spread treats both pages as one 4-column grid — two equal columns a page, the same measure and top margin on each — and flows the text across it; the photograph fills what the text leaves.
- **Baseline:** 12 pt baseline grid; align body text and list items to it.
- **Vertical zones:** describe image placement as page-height percentages (top = 0%). The half-page bands are upper 0–50%, centered 25–75%, lower 50–100%, each with ~5 pt of visual tolerance.

## Type Hierarchy

Committed pairing: **Playfair Display** (display serif — titles, pull quotes, and the attribution italic) + **Source Sans 3** (humanist sans — body, section headers, metadata chips). Both are open-source SIL OFL variable fonts, stored in the engine's `fonts/` (with their `OFL-*.txt` licenses) and embedded as base64 `@font-face` by the engine's `render.py`, so the draft is self-contained. Keep the roles and relative scale if the pairing is ever swapped.

| Style | Font role | Size / leading | Use |
|-------|-----------|----------------|-----|
| Title | Display serif, bold | 34–44 pt / 1.05 | Recipe name |
| Title (long) | Display serif, bold | 26–32 pt | Titles over ~24 chars |
| Attribution | Accent italic | 14–16 pt | "*Ruth Baker*" credit line |
| Section header | Sans, small caps, tracked | 11–12 pt | INGREDIENTS / DIRECTIONS |
| Metadata chip | Sans, medium | 9–10 pt | Category, yield, prep, cook, temp |
| Body — ingredients | Sans, regular | 10.5–11 pt / 14 pt | Bulleted ingredient list |
| Body — directions | Sans, regular | 10.5–11 pt / 15 pt | Numbered steps |
| Pull quote | Display serif or accent italic | 18–22 pt | One lifted line, accent color |
| Caption | Sans, italic | 8.5–9 pt | Image or variant captions |
| Footer link | Sans, regular, underlined | 9 pt | "View the original recipe" |

## Category Color Accents

One accent per section, used on rules, section headers, metadata chips, pull quotes, or a header band — never as large fills behind body text. Values are warm, print-friendly starting points.

| Category | Accent | Hex |
|----------|--------|-----|
| appetizers | terracotta | `#C1663F` |
| breads-pancakes-and-french-toast | wheat gold | `#C79A3B` |
| casseroles | paprika red | `#B0472F` |
| desserts | rose plum | `#B15574` |
| drinks | teal | `#2E7D82` |
| eggs | warm yolk | `#D9A441` |
| fish-and-shellfish | slate blue | `#4E6E87` |
| meat | deep bordeaux | `#7E3B3B` |
| pasta | tomato clay | `#B85742` |
| poultry | sage olive | `#7A8450` |
| quick-meals | bright coral | `#D9694F` |
| salads-dressings-and-sauces | garden green | `#5E8C4A` |
| sides | butternut | `#C08540` |
| soups-and-stews | pumpkin | `#B96B34` |
| other-family-secrets | dusty violet | `#7C6A94` |
| intro | ink neutral | `#3F3A34` |

If a category is missing from this table, fall back to the ink neutral `#3F3A34` and note it in the spec.

## Standard Page Anatomy

Unless an archetype overrides it, a recipe page stacks:

1. **Header** — title, attribution italic, then a thin accent rule and the metadata chips.
2. **Image** — in the archetype's reserved zone.
3. **Ingredients** — accent section header, then the bulleted list.
4. **Directions** — accent section header, then numbered steps.
5. **Footer** — the "View the original recipe" link, right- or left-aligned in the bottom safe margin.

Match the source recipe's markdown order and content exactly; this skill arranges, it never rewrites.
