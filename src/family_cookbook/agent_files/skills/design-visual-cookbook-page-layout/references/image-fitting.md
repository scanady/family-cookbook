# Image Fitting — Derive, Don't Regenerate

Layouts need images at different frames (full-bleed portrait, half-page band, tall sidebar strip, inset). A single generated photo rarely fits every archetype. When the chosen archetype's frame doesn't match the existing image, resolve it with the **cheapest sufficient** method — climb to a costlier tier only when the one below genuinely fails. Image generation over a whole book is expensive; this ladder keeps almost every page free.

Since recipe photos are generated separately and land independently, treat the existing image as a **fixed input**: the layout adapts to it, and a new or altered image is requested only when the existing one truly can't be made to work.

## The tier ladder

| Tier | Method | Cost | Use when |
|------|--------|------|----------|
| 0 | **Fit the layout to the image** — pick an archetype whose frame the existing image already satisfies | free | Always try first; a portrait dish photo already fits Half-Page (upper/centered/lower) |
| 1 | **Deterministic manipulation** — crop / pad onto a neutral matte / gradient scrim for title legibility / accent-tune, via Pillow | free (no AI) | The image is usable but the frame differs: square → sidebar strip, → inset, → full-bleed hero |
| 2 | **Generative extension** — outpaint/extend the *existing* image's background to an aspect cropping would ruin | paid, per image | Tier 1 can't preserve the subject (e.g., true full-bleed where the subject fills the frame). Opt-in only |
| 3 | **Full regeneration** | highest | No usable base image exists at all |

At book scale the overwhelming majority of pages resolve at Tier 0–1 (free). Only genuine frame conflicts (mainly full-bleed subject preservation) reach a paid tier.

## Guardrails

- **Never touch the original.** Write derived variants beside it as `{slug}-{key}.jpg`; the original stays the reusable source.
- **Cache.** Skip a variant that already exists and is newer than its source, so a tier is paid at most once per (recipe × frame), never on rebuild.
- **No upscaling.** Deterministic crops are taken at the source's native resolution. Faking print resolution by enlarging is not allowed — instead, report which crops fall below print resolution so the fix (a higher-res image) is a visible, deliberate choice.
- **Make paid tiers explicit.** Before any paid step, tell the user the required aspect ratio, whether the existing image satisfies it, the transform needed, and the tier that transform costs. A paid extension must never happen silently.

## Implementation in the engine

`cookbook fit` performs Tier 0–1 for free: for each recipe on a fixed-size frame (the sidebar column, the Two-Page Spread's photo leaf), it crops the existing image to that frame's aspect (native resolution, never upscaled) and saves `{slug}-{key}.jpg`. The engine's `render.py` then prefers the fitted variant over the base image.

The band (Half-Page Classic, Inset Original) and the hero have **no fixed size** and no crop file: the photo takes all the height the text leaves on the page, within a range (band 3–6.75 in, hero 5–7.25 in; `PHOTO_RANGE`). The page carries the canonical image with its crop windows precomputed for a run of heights (`photo_windows()`, in `data-windows`), and once `FIT_SCRIPT` has laid the page out it gives the photo the window nearest its measured aspect through CSS `object-view-box` — the same window `photo_fit()` judged. Python predicts the height the text will leave (`photo_room()`, a text-height model calibrated against the press build) to choose the layout and to judge the frame at that size.

The crop follows the dish. `photo_subject()` in the engine's `render.py` finds it in the photo — the region of fine detail and saturation that the plain backdrop lacks, damped where the color matches the photo's border, weighted toward its most detailed part (the meatballs, not the bowl) — and also measures the dish's full extent — following the photo's outlines out from the dish so a glass's rim and foot, a pint's head, or a cake's pale crown are included — and any flat padding above or below a photo set on a larger canvas. `subject_crop()` then cuts the window:

- **Band and column frames are tightened** to the smallest window of the frame's aspect that holds the dish's whole extent with `DISH_AIR` (30% of its size) around it, but never so small that it prints under 300 ppi (`PRINT_PPI`) — so a small dish is not lost in backdrop.
- **Otherwise the window is the largest one** the photo allows — always for full-bleed frames, whose backdrop is part of a full-page picture, and wherever the dish is too big to tighten around — centering the dish when it fits and otherwise holding the most of the food, but never cutting through the subject's top: a dish too tall for the window loses its foot instead.
- **No window crosses a padding seam** when it fits inside the photo proper.

The same detection sets each `<img>`'s CSS `object-position`, so a frame that `object-fit` trims further keeps the dish in view. A recipe's `- **Image position:** top|center|bottom` overrides the vertical placement (and skips the tightening); set it only when the rendered crop misses the dish.

Whether a frame shows the dish also steers layout selection (`photo_fit()`). The food and its vessel are judged apart: a frame may crop a bowl's side or a plate's edge, but never the food, and never through the subject's top (a glass's rim, a pint's head, a cake's crown). The hero and spread show the whole food (`FOOD_WHOLE`); the band holds at least `BAND_FOOD_HELD` (55%) of the food's mass, so a short band may trim the outer edge of a deep dish but keeps its body; the sidebar only takes a narrow, standing subject it shows whole across (`COLUMN_FOOD`) and filling the column (`COLUMN_FILL`), and such a standing subject keeps its whole silhouette in the other frames too (`STANDING_WHOLE`). Auto-assignment skips a frame that breaks these. A photo never costs a page: a short recipe whose photo suits no one-page frame takes the band or hero showing the most food, and `cookbook fit` lists it as a candidate for a regenerated photo — the Tier 2–3 signal. Variants are cached (stamped with the crop window they were cut with), stale ones from a prior archetype are cleaned up, and crops below print resolution are reported.

Frame keys, sizes in the press build, and kinds (see `PHOTO_FRAMES` in the engine's `render.py`):

| Archetype | Key | Frame (in) | Kind |
|-----------|-----|------------|------|
| Two-Page Spread (photo leaf) | `spread` | 8.75 × 11.25 | full-bleed |
| Sidebar Portrait | `sidebar` | 3.10 × 7.71 | column |
| Hero Full-Bleed | — (canonical image, framed in the browser) | 8.75 × 5–7.25 | full-bleed |
| Half-Page Classic, Inset Original | — (canonical image, framed in the browser) | 7.0 × 3–6.75 | band |
| Recipe Spread | — (canonical image, trimmed in place) | text-dependent | — |

Tier 2–3 (generative) are intentionally **not** implemented here — they are the opt-in escalation to `design-visual-cookbook-image-generator`, invoked only when Tier 0–1 cannot satisfy the frame.
