---
description: "Use when creating, transcribing, normalizing, or editing cookbook recipes, ingredients, directions, notes, metadata, and recipe source files."
applyTo: "book/recipes/**"
---
# Recipe Content

Each food recipe lives at `book/recipes/{category}/{slug}/`:

- `recipe.md`: clean source of truth
- `sources/recipe-original.md`: optional verbatim transcription
- `images/{slug}.jpg`: optional canonical finished-dish photo
- `prompts/{slug}-image-prompt.md`: optional image prompt
- `prompts/{slug}-layout.md`: optional written layout note; the engine never reads it, and only `cookbook lint` checks that a `layouts:` row's `spec:` path exists
- `extras/`: optional keepsakes (card scans, family photos); only files listed in `extras/extras.md` as `![Caption](file.jpg)` lines print — see the `cookbook-extras` skill

Create none of these folders empty, `extras/` included.

Use this structure in `recipe.md`, omitting optional sections and files when absent:

```markdown
# Title

*Author Name*

![Title](images/{slug}.jpg)

- **Category:** ...
- **Cuisine:** ...
- **Yield:** ...
- **Prep time:** ...
- **Cook time:** ...
- **Temperature:** ...

## Ingredients

- item

**Sub-recipe Name:**
- item

## Directions

1. step

## Notes

- note

[View the original recipe](sources/recipe-original.md)
```

- Always use `## Ingredients` and `## Directions`, including recipes written in a loose family voice.
- Put stories, tips, and serving suggestions in `## Notes`, not directions. Omit yield-only direction steps when Yield metadata already states it.
- Write **Cook time** as one total duration in `{x} hour {y} minutes` form: `45 minutes`, `1 hour`, `1 hour 30 minutes`, `2 hours 15 minutes`. Sum every timed stage (stovetop, oven, simmer) instead of listing them. Write a range as `{a} to {b}` (`1 hour to 1 hour 15 minutes`), prefix `About` when the source approximates, and use `Not specified` when the source gives no time.
- Use bold subheads only inside Ingredients. Directions must remain one sequentially numbered list; fold phase names into step text.
- Normalize faithfully from `sources/recipe-original.md`. Never invent amounts or ingredients.
- Write fractions in ASCII, `1/2` and `1 3/4`, not `½` or `1¾`; the verbatim transcription keeps the source's glyphs.
- Fix clear OCR artifacts, but preserve the source's wording quirks.
- Never hand-edit generated `{slug}-{sidebar|spread}.jpg` crops.
- Leave `- **Image position:**` out by default: the renderer finds the dish in the photo and crops around it. Add it (`top`, `center`, or `bottom`, after the Temperature line) only as an override for a photo whose rendered crop misses the dish.