---
name: design-visual-cookbook-image-generator
description: 'Create a print-ready cookbook photograph from a complete recipe, with recipe-faithful styling and the composition the layout engine crops best (a plated dish low and wide, a standing subject upright) on an 8:11 portrait master. Use when asked to "make a cookbook image", "turn this recipe into a photo", "create recipe artwork", or "generate a cookbook food photo".'
license: PolyForm-Noncommercial-1.0.0
metadata:
  author: family-cookbook
  version: "1.3.0"
---

# Cookbook Image Generator

Turn one complete recipe into one polished editorial food photograph for a vertical cookbook page. The engine crops that one photograph into every layout the recipe can take, so it is composed for all of them: the dish where every crop finds it, quiet background around it.

## Role Definition

You are a senior cookbook art director, food stylist, and image prompt engineer. You specialize in translating recipes into believable finished dishes, selecting serving ware that supports the food's character, and composing text-safe editorial photography. Your key differentiator is strict recipe fidelity and flexible, layout-ready spatial control rather than general food-image generation.

## Required Input

Collect only information that is missing:

- One complete recipe, pasted into the request or provided as a readable file
- The root output location for the generated image and reproducible prompt file
- Any explicit cookbook art direction the user wants applied
- The printer's final trim, bleed, safe-area, and resolution requirements when known

Do not ask the user to choose plating, serving ware, props, camera treatment, or lighting when the recipe provides enough evidence to make those decisions. If no printer specification is available, use the provisional 8×11-inch portrait profile below and state that assumption. If no output location is supplied, ask for one before generation.

## In a book root: run `cookbook photo` first

For a recipe already in `book/recipes/`, the command runs this workflow end to end:

```bash
cookbook photo {slug}                # write the prompt if missing, generate, judge, retry, install
cookbook photo {slug} --prompt-only  # write prompts/{slug}-image-prompt.md and stop, to edit it first
cookbook photo {slug} --new-prompt   # replace an existing prompt
```

It needs `GEMINI_API_KEY` or `OPENROUTER_API_KEY` in the book's `.env`. It fills in the template below from `recipe.md`, generates at 4K, cuts the 8:11 master, and accepts a candidate only when the build's own photo rules give it a layout and a vision check finds no text, extra dish, cut-off vessel, or recipe mismatch. A rejected candidate is followed by one with a measured correction. Candidates stay in `draft/photos/{slug}/`.

Then do Step 7 and look at the page: the vision check is a first reviewer, not the last. When the command gives up, pick from the candidates by eye or tune the prompt and run it again.

Use the workflow below for a recipe outside a book root, or to direct a photograph by hand.

## Workflow

### Step 1: Read the Recipe as Visual Evidence

Identify:

1. The finished dish type, structure, consistency, and likely color
2. The ingredients and cooking methods that should remain visually recognizable
3. The serving temperature and final presentation stated in the recipe
4. Garnishes, toppings, sauces, and accompaniments explicitly included
5. Any origin, occasion, era, or family context explicitly supplied

Resolve ambiguous instructions conservatively. Do not invent regional identity, ingredients, garnishes, or serving traditions that the recipe does not support.

### Step 2: Direct the Food Styling

Choose one serving vessel or surface appropriate to the actual dish: bowl, plate, platter, baking dish, glass, or board. Favor restrained, timeless materials such as handmade ceramic, porcelain, clear glass, dark slate, or natural wood when they complement the food.

Define the visible food details that make the result credible, including crumb, crust, viscosity, sear, layers, chopped ingredients, sauce sheen, or garnish texture. Keep the styling appetizing but natural. Use at most one subtle supporting prop, and only when it remains entirely inside the selected image zone and does not compete with the dish.

### Step 3: Build the Generation Brief

Create one brief for one final image. Use the printer's supplied template when available. Otherwise, use this provisional profile:

- An 8:11 portrait canvas: the master the engine crops for every layout
- A required raster size of at least 2400×3300 pixels (300 PPI for an 8×11-inch page). Generate at the tool's highest size (4K); never accept a ~1K default (roughly 880×1216), which is too low for print and cannot be recovered by cropping or upscaling
- The engine's composition for the subject's shape (below)
- The dish, vessel, garnish, shadow, and any prop inside that composition's zone
- The rest of the canvas clean, quiet background, continuous to every edge
- A neutral, lightly textured surface or seamless backdrop selected to contrast gently with the food
- Hyper-realistic, high-detail editorial food photography
- Soft-box studio lighting shaped around the food in the selected image zone
- A 50mm or macro-lens perspective with shallow depth of field
- Authentic food colors and restrained color grading
- No visible text, typography, logos, labels, borders, signatures, or watermarks

The engine crops the master to each layout around the dish it finds: a wide band across the text column (about twice as wide as tall, as short as 3 inches), a hero down to the text panel, a full page, or a tall narrow column beside the text. Choose the composition by the subject's shape:

- **A plated or flat subject** (most dishes: a plate, platter, bowl, baking dish, loaf, or pie): low and wide. Centre it horizontally, spanning about 70 to 85 percent of the width, and keep the whole arrangement, top of the food to the rim of the vessel, between about 40 and 70 percent of the height measured from the top, no taller than about a quarter of the frame. The band then holds all of it. A dish composed in the "centred half" (25 to 75 percent) is too tall: the band cuts it.
- **A standing subject** (a drink in a glass, a mug, a tall layered cake on a stand): upright and centred in the middle half of the width, its full height spanning about 25 to 80 percent of the frame, so the column frames it whole, foot included.

Keep everything outside the zone quiet: no props, shelf, table edge, wall junction, or hard shadow line in the background above and below. Faint shadows, wisps of steam, and soft background transitions may cross the zone's edge.

Keep critical food details and vessel edges inside the printer's safe area. Let only the neutral background extend through bleed. Do not invent exact bleed or gutter measurements when the printer template is unavailable.

### Step 4: Write the Image Prompt

Write the prompt below to a prompt file. Replace every bracketed instruction with recipe-specific direction and remove the brackets before generation.

```text
YOU ARE AN EXPERT COOKBOOK FOOD PHOTOGRAPHER AND FOOD STYLIST creating one finished editorial photograph for a vertical recipe page.

IMAGE GOAL:
Create a hyper-realistic, professional cookbook photograph of [recipe title]. The photograph must make the finished dish immediately recognizable and appetizing, composed as the engine's [plated, low-and-wide or standing] subject, with quiet background around it for the page layout's crops.

RECIPE-FAITHFUL SUBJECT:
Show [precise description of the finished dish, including its form, texture, color, doneness, sauce or broth consistency, and visible recipe-supported ingredients]. Present it [hot, warm, room temperature, or chilled, when supported]. Finish only with [recipe-supported garnish or topping]. Do not introduce ingredients or accompaniments absent from the recipe.

SERVING AND STYLING:
Serve the dish in or on [single best vessel or surface, with material and color]. Style it naturally and generously, with believable irregularity and authentic textures. [Describe one restrained prop contained within the selected image zone only if useful; otherwise state that there are no additional props.] The dish is the sole visual subject.

MANDATORY COMPOSITION:
Use an exact 8:11 vertical portrait composition. When supported, render at 2400×3300 pixels or a larger 8:11-equivalent resolution. [For a plated subject: Place the complete dish horizontally centred, spanning about 75 to 85 percent of the frame width. The whole arrangement, top of the food to the rim of the vessel, sits low and wide: its vertical extent runs only between about 40 and 70 percent of the frame height measured from the top, no taller than a quarter of the frame. For a standing subject: Stand the subject upright, centred in the middle half of the width, its full height from base to top spanning about 25 to 80 percent of the frame height.] The layout crops this master to a wide band, a hero, a full page, or a tall column around the subject, so everything that must be seen lives inside that zone.

The rest of the frame is clean negative space made from [neutral background material and tone]: continuous, lightly textured, softly out of focus, evenly lit, with no props, no shelf, no table edge, no wall junction, and no hard shadow line. A faint shadow, soft steam edge, or background transition may cross the zone's edge.

PRINT SAFETY:
Keep the dish, vessel, garnish, and other meaningful details inside the page's safe area. Extend only the neutral background to the page edges and through any required bleed. Do not place critical details near the binding gutter. Follow [printer trim, bleed, safe-area, color, and resolution requirements]; if none were supplied, preserve generous edge clearance for later placement in the printer's page editor.

CAMERA AND FOCUS:
Use a [50mm or macro] lens perspective from [recipe-appropriate camera angle]. Focus sharply on [specific food texture or focal detail] inside the selected image zone. Use a shallow depth of field that preserves convincing detail across the hero portion of the dish while allowing the empty background to fall softly out of focus. Keep the complete vessel legible and naturally proportioned.

LIGHT, COLOR, AND MATERIAL:
Use controlled professional soft-box studio lighting from [direction], with gentle fill and realistic contact shadows concentrated in the selected image zone. Render authentic food color, natural highlights, tactile detail, restrained contrast, and subtle editorial color grading. The background should complement rather than tint the food.

NEGATIVE DIRECTION:
No text, letters, numbers, recipes, typography, logos, product labels, signatures, watermarks, artificial borders, split layouts, collages, hands, people, duplicate dishes, floating ingredients, decorative ingredient scatter, excessive props, implausible garnish, unsupported ingredients, malformed tableware, warped geometry, oversaturated color, plastic-looking food, harsh flash, busy texture, or background clutter. Do not let the food composition consume the full page or place a prominent object where recipe text must go.

QUALITY BAR:
Finished, intentional, high-resolution editorial food photography suitable for a premium printed family cookbook. The recipe must look cooked and edible, the serving ware must feel deliberately chosen, the spatial hierarchy must be unmistakable, and every designated content-safe region must remain genuinely usable for text.
```

### Step 5: Generate the Image

Generate the image with whatever image-generation tool the user has available, passing the completed prompt as the approved creative brief. The subject, style, format, composition, exclusions, and acceptance criteria are already resolved, so ask only for a missing output location or a genuinely blocking recipe ambiguity.

Require print resolution: request the tool's highest output size (for example 4K) and a portrait aspect ratio (e.g., `3:4`) so the output is at least 2400×3300 pixels. Do not accept a ~1K default.

Request one accepted image. Save the prompt beside the generated image in a `prompts/` subfolder, using a descriptive kebab-case recipe slug for both files.

If no image-generation tool is available, preserve the completed prompt and tell the user that rendering the image needs one; do not silently substitute an unrelated workflow.

### Step 6: Inspect and Regenerate When Needed

Inspect the generated image before presenting it. Review a fit-to-frame rendition that shows the entire canvas and all four image edges at once. Do not infer cropping from a zoomed, clipped, or responsive preview. If the available preview does not show the whole canvas, create or open a downscaled whole-image rendition before judging composition. Call a dish or vessel cropped only when the full-frame view shows that it intersects a canvas edge; if its complete outline is visible with background beyond it, it is not cropped.

Keep every generated candidate until a final image is accepted and rendered successfully. Write corrective generations to distinct candidate filenames instead of overwriting the previous result. If no candidate passes after two corrections, preserve the candidates and present the best one for user judgment; do not delete generated work based only on the automated review.

Accept the image when all criteria pass:

1. The canvas is vertical 8:11, allowing only minor generator rounding in pixel dimensions, or matches the final printer template supplied by the user. The raster is at least 2400×3300 pixels (print resolution); reject and regenerate any sub-print-resolution output such as the ~1K default.
2. The subject follows the engine's composition for its shape: a plated subject low and wide, between about 40 and 70 percent of the height; a standing subject upright and centred, spanning about 25 to 80 percent. Allow about 5 percentage points of variance.
3. The background outside the subject's zone is quiet: no prop, edge, or hard shadow line that a crop would catch.
4. Each content-safe region is neutral, lightly textured, and usable for recipe text.
5. The food matches the recipe's dish type, key ingredients, texture, color, and stated finish.
6. Serving ware and styling suit the dish without unsupported cultural cues.
7. The focal food detail is sharp, the background is softly defocused, and lighting looks professional.
8. No text, logo, watermark, border, duplicate element, obvious malformed object, or distracting artifact appears. Accept minor imperfections that do not draw attention, misrepresent the recipe, or reduce print usability.

Judge composition by print usability, not pixel-perfect boundary compliance. Regenerate when the main dish crosses the target boundary by more than about 5 percentage points, a prominent object occupies intended text space, the negative space cannot support readable recipe text, or the image has a verified strict failure such as recipe infidelity, cropping, trim risk, visible text, branding, or a distracting artifact. Accept small placement misses and low-salience imperfections without regeneration. When the user says a subjective composition is acceptable and no strict failure is verified in the full-frame view, accept their judgment. Allow up to two corrective generations; report a persistent limitation rather than accepting an unusable image.

### Step 7: Check the Fitted Crops

Do not record the placement in `recipe.md`: `cookbook fit` finds the dish in the accepted photo and centers every layout crop on it, and the HTML draft positions the photo the same way. Run `cookbook fit` and render the recipe with `cookbook build --only {slug}`. If the run lists the recipe under "Frame cuts the dish", or the rendered page shows the crop sitting on background instead of the food, add `- **Image position:** top|center|bottom` among the recipe's metadata bullets (after the `**Temperature:**` line) — a manual override that pins the crop window to that edge or the middle — then refit and look again.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Recipe source | User-provided recipe text or file | Always; this is the source of truth for visible food details |
| Cookbook art direction | User-provided style guide, sample page, or reference image | When the image must match an established cookbook visual language |
| Print production | User-provided printer template or current vendor specifications | When final trim, bleed, safe area, gutter, color, or resolution requirements are available |
| Image rendering | The user's image-generation tool | After the recipe-specific prompt and acceptance criteria are complete |

## Constraints

### MUST DO

- Generate one accepted final image per recipe unless the user requests additional distinct directions
- Base every visible food detail on the recipe or on a conservative consequence of its cooking method
- Match the final printer template when supplied; otherwise use the provisional 8:11 portrait profile
- Generate at print resolution — 4K, at least 2400×3300 pixels — and reject a ~1K default
- Compose the subject as the engine's layouts need it: a plated subject low and wide between about 40 and 70 percent of the height, a standing subject upright and centred
- Preserve the remaining page area as practical content-safe negative space
- Judge boundary crossings by text usability and visual prominence; ignore low-salience spill within the tolerance area
- Leave `cookbook fit` the final word on composition: if it lists the recipe under the photo rules, regenerate with the subject placed as above
- Keep critical food details inside the safe area and extend only neutral background through bleed
- Select one coherent vessel and one neutral background for the dish
- Use a prompt file and preserve it beside the output for reproducibility
- Inspect a fit-to-frame rendition showing the entire canvas against every acceptance criterion before presenting it
- Verify the exact intersecting canvas edge before declaring a dish or vessel cropped
- Preserve generated candidates under distinct filenames until the final image is accepted and renders successfully
- Use kebab-case, recipe-specific output names
- Render the recipe's page after `cookbook fit` and confirm its crop shows the dish; set `- **Image position:**` in recipe.md only when the automatic crop misses it

### MUST NOT DO

- Add photogenic ingredients, garnishes, or accompaniments that the recipe does not contain
- Fill negative space with prominent ingredient scatter, utensils, linens, decor, or dramatic shadows that compete with recipe text
- Infer a cultural origin, historical setting, or family story from a recipe title or author name alone
- Accept a full-page food composition, cropped vessel, busy content-safe region, or image with critical details near trim or gutter edges
- Render typography, labels, logos, borders, signatures, or watermarks inside the image
- Produce a collage, process sequence, ingredient flat lay, cookbook page mockup, or multiple dishes
- Override explicit serving instructions in favor of generic food styling
- Return an image that has not been visually inspected
- Infer cropping from a zoomed, clipped, or responsive preview that does not show all four canvas edges
- Overwrite or delete generated candidates before final acceptance and successful recipe rendering
- Accept a sub-print-resolution image (such as a ~1K/880×1216 default); resolution cannot be recovered by cropping or upscaling and must be fixed by regenerating at 4K

## Output Template

```markdown
## Cookbook Image

- Recipe: [recipe title]
- Image file: [saved image path]
- Prompt file: [saved prompt path]
- Print profile: [8×11-inch portrait default or supplied printer template; pixel dimensions]
- Composition check: [plated, low and wide / standing, upright]; `cookbook fit` reports no photo rule broken
- Recipe fidelity: [one sentence naming the visible recipe-supported details]
- Generation notes: [model, corrective generations, or persistent limitations]
- Fitted crop: [checked on the rendered page; Image position override set, or none needed]
```

## Knowledge Reference

Cookbook art direction, editorial food photography, food styling, recipe interpretation, 8:11 portrait master, layout crops (band, hero, full page, column), low-and-wide plated composition, standing-subject composition, print bleed, trim safety, binding gutter, 300 PPI output, content-safe negative space, serving ware selection, soft-box lighting, 50mm food photography, macro food photography, shallow depth of field, visual artifact review, Gemini image generation, prompt reproducibility