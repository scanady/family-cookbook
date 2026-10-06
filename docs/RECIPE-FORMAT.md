# Writing the book: recipes, pages, photos, and keepsakes

Everything that prints comes from plain files under `book/`. This page
describes each kind of file and what the engine does with it. After any change,
`cookbook lint` checks the structure and `cookbook build` shows the result in
`draft/cookbook-draft.html`.

- [Where things live](#where-things-live)
- [Recipes: recipe.md](#recipes-recipemd)
- [Dish photos: images/{slug}.jpg](#dish-photos-imagesslugjpg)
- [The original: sources/recipe-original.md](#the-original-sourcesrecipe-originalmd)
- [Prose entries: page.md](#prose-entries-pagemd)
- [Chapter opening pages](#chapter-opening-pages)
- [Dedication and closing message](#dedication-and-closing-message)
- [The back cover: book/cover.md](#the-back-cover-bookcovermd)
- [Keepsakes: extras/](#keepsakes-extras)
- [Placeholder text](#placeholder-text)

## Where things live

```
book/
  book.yaml                                   chapters, colors, cover settings (BOOK-YAML.md)
  cover.md                                    back-cover blurb and sign-off
  recipes/{chapter}/{slug}/
    recipe.md                                 the recipe
    images/{slug}.jpg                         its dish photo (optional)
    sources/recipe-original.md                the original, word for word (optional)
    sources/original-1.jpg ...                scans of the original (written by cookbook ingest)
    prompts/{slug}-image-prompt.md            the prompt cookbook photo uses (optional)
    extras/extras.md + files                  keepsakes (optional)
  sections/{chapter}/
    page.md                                   the chapter's opening message, or a one-page chapter
    extras/                                   the chapter's keepsakes (optional)
  sections/{chapter}/{slug}/
    page.md                                   a prose entry: a story, a tip, a poem
    sources/page-original.md                  its original (optional)
    extras/                                   its keepsakes (optional)
```

A **slug** is an entry's folder name: lowercase words joined by hyphens, such
as `skillet-cornbread`. Lint reports any other form as an error. Do not leave
empty folders; lint reports those too.

Recipe chapters (`kind: recipes` in `book.yaml`) keep their entries under
`book/recipes/`; prose chapters (`kind: prose`) keep theirs under
`book/sections/`. Every chapter's own opening page lives under
`book/sections/{chapter}/`, whichever kind it is.

## Recipes: recipe.md

A complete recipe, with every optional part:

```markdown
# Skillet Cornbread

*Ruth Baker*

![Skillet Cornbread](images/skillet-cornbread.jpg)

- **Category:** Mains
- **Cuisine:** Southern
- **Yield:** One 10-inch round
- **Prep time:** 10 minutes
- **Cook time:** 20 minutes
- **Temperature:** 425°F

## Ingredients

- 1 cup cornmeal
- 1 cup buttermilk
- 1 egg

**For the skillet:**
- 2 tablespoons bacon fat

## Directions

1. Heat the oven to 425°F with the fat in a cast-iron skillet.
2. Stir the cornmeal, buttermilk, and egg together.
3. Pour into the hot skillet and bake until golden, about 20 minutes.

## Notes

- Grandma never measured the fat.

[View the original recipe](sources/recipe-original.md)
```

What the engine does with each part:

| Part | Required | What happens |
|---|---|---|
| `# Title` | yes | The recipe's title, in the contents and the index. The file must start with it (lint error otherwise). |
| `*Name*` | no | The **attribution**: an italic line directly under the title. It prints under the title and builds the Contributors page and the index. |
| `![Title](images/{slug}.jpg)` | no | A link for people reading the markdown. The engine finds the photo by its file name, not by this line. Lint warns if the photo exists and the line is missing, and if the link points anywhere else. |
| `- **Key:** value` lines | no | Small labeled details under the title (see the table below). |
| `## Ingredients` | yes | A list of `- item` lines. A line like `**For the frosting:**` starts a subhead within the list. Lint error if the section is missing. |
| `## Directions` | yes | One numbered list, `1.`, `2.`, `3.` in order. Lint errors if the numbers skip or restart, or if a bold subhead sits inside it: put stage names ("For the sauce") into the step text instead. |
| `## Notes` | no | Stories, tips, and serving suggestions. `- ` bullets or plain lines. |
| `[View the original…](sources/recipe-original.md)` | no | A link for people; not printed. Lint warns if the original exists and the link is missing, and errors if the link points to a missing file. |
| any other `## Heading` | — | **Not printed.** The heading and everything under it, up to the next `## Ingredients`, `## Directions`, or `## Notes`, is dropped from the book. |
| text outside the sections | — | Not printed on a recipe. Put it in Notes. |

### Recipe details

| Key | What it is |
|---|---|
| `Category` | The chapter's name, for people. Not printed. |
| `Cuisine` | Printed. |
| `Yield` | Printed. `cookbook audit` warns if the original does not state it (see `audit: estimates` in [BOOK-YAML.md](BOOK-YAML.md#audit)). |
| `Prep time` | Printed. Checked like Yield. |
| `Cook time` | Printed. Write one total, `{x} hour {y} minutes`: `45 minutes`, `1 hour 30 minutes`. Add up every timed stage. Write a range as `1 hour to 1 hour 15 minutes`, and start with `About` when the original only estimates. The audit checks it against the times in the directions. |
| `Temperature` | Printed. The audit checks it against the directions and the original. |
| `Chill time`, `Total time`, `Source` | Printed. |
| `Image position` | Not printed. `top`, `center`, or `bottom`: moves the photo's crop when the automatic crop misses the dish (see [LAYOUTS.md](LAYOUTS.md#photo-crops)). Leave it out unless you need it. Lint error for any other value. |

A value of `Not specified` or `Not applicable` is not printed. Any other key
prints too, but lint warns about it, because it is usually a typo
(`Prep Time`, `Serves`). A key with no value draws a lint warning: leave the
line out instead.

Write fractions as `1/2` and `1 3/4`, not `½`. The original keeps its own
characters.

### Credits that split

The attribution line feeds the Contributors page, so write joint credits so
they split into people:

- `Ann Lee and Bob Lee`, or `Ruth and Tom Baker` (the surname is shared)
- `Ruth Baker/Jane Baker`
- `Jane Baker (submitted by Tom Baker)` credits Jane only.

## Dish photos: images/{slug}.jpg

Each recipe has at most one dish photo, at exactly
`images/{slug}.jpg` in its folder (a `.jpg` file named after the slug). The
engine picks the layout and crops the photo around the dish on its own. Any
other file in `images/` is never used; lint warns about it. Files ending in
`-sidebar.jpg` or `-spread.jpg` are crops that `cookbook fit` makes. They are
rebuilt from the original, so never edit them.

Size and shape:

- **Portrait (taller than wide).** A page is 8.5 × 11 in, and the largest
  frames are a full page and a wide band. A 3:4 photo works well.
- **At least 2625 × 3375 pixels.** The largest frame, a full-page photo with
  bleed, is 8.75 × 11.25 in, and print needs 300 pixels per inch. Photos made by
  `cookbook photo` are about 3500 × 4800.
- **Leave space around the dish.** The engine tightens or widens the crop to
  fit each layout, and needs room to do it.

`cookbook fit` (part of `cookbook press`) lists any photo too small for crisp
print where it lands, and any frame that cuts the dish. For either, use a
larger or better-framed photo, set `Image position`, or choose a different
layout ([LAYOUTS.md](LAYOUTS.md)).

A prose entry may have a photo too, at `sections/{chapter}/{slug}/images/{slug}.jpg`.

## The original: sources/recipe-original.md

The word-for-word transcription of the recipe as it was written: spelling,
abbreviations, and all. `cookbook ingest` writes it; you can also write it by
hand. The engine reads only the **first** fenced block marked `text`:

````markdown
# Skillet Cornbread

*Ruth Baker*

Ruth's recipe card, about 1975.

## Original Recipe

```text
CORN BREAD
1 c. meal, 1 c. buttermilk, 1 egg
Bake in hot greased skillet 20 min.
```

[View the updated recipe](../recipe.md)
````

Everything outside that block is for people. The block is used in three
places:

- the **Inset Original** layout prints it beside the recipe;
- `cookbook audit` compares the recipe against it (cook time, invented
  amounts, dropped lines);
- `cookbook review` shows it next to the recipe while you check it.

A recipe without an original still prints. The audit just has less to check.

## Prose entries: page.md

A story, a household tip, a poem, a letter: anything that is not a recipe. It
lives in a prose chapter at `book/sections/{chapter}/{slug}/page.md`:

```markdown
# Sunday Dinners

*Ruth Baker*

Every Sunday after church the whole family came to the farm.

The kitchen table seated eight, so the children ate on the porch.

### What we always had

- Fried chicken
- Biscuits
```

- `# Title` first (required), then an optional italic attribution line.
- **Each line is one paragraph.** Write a paragraph on a single line, and put
  a blank line between paragraphs.
- `- ` lines become a bulleted list, `### Heading` a small heading, and `---`
  a rule. `**bold**` and `*italic*` work inside a line.
- Do not use `##` headings: a `##` heading other than `## Notes` drops
  everything under it.
- A long page continues onto the next page on its own.

The original, if you keep one, is `sources/page-original.md`, in the same
format as a recipe's.

## Chapter opening pages

A chapter with `divider: true` in `book.yaml` (the default) opens with a
divider page on a right-hand page: the chapter's label in its accent color.
To add a message under the label, write `book/sections/{chapter}/page.md`:

```markdown
*The recipes we make every Thanksgiving, and the people who taught us.*
```

- **No `#` heading.** The heading is the chapter's `label` from `book.yaml`, the
  same words the contents prints. A heading here is a lint error.
- A page that is one italic line is set as a message under the label.
- The file is optional. Without it, the divider shows the label alone. An
  empty file is a lint error: write the message or delete the file.

`cookbook init` writes one of these with a `TODO` placeholder for every
chapter.

## Dedication and closing message

These are one-page chapters: `kind: prose` and `divider: false` in `book.yaml`,
with their text at `book/sections/matter-dedication/page.md` and
`book/sections/matter-closing-message/page.md`. They follow the chapter-page
rules: no `#` heading (the label is the heading), one paragraph per line. A
one-page chapter cannot also hold entries; lint reports any that would never
print.

## The back cover: book/cover.md

```markdown
# Back Cover

Recipes from four generations of Smiths, gathered for everyone who ever
sat at Grandma's table.

*With love, the Smith family*
```

- The `#` heading is ignored.
- The other paragraphs become the blurb. Unlike pages inside the book, line
  breaks here are joined, and all the paragraphs print as one block.
- A paragraph that is one `*italic*` line becomes the sign-off.

Lint warns when the blurb or the sign-off is missing. The front cover, the
spine, and their colors are set in `book.yaml` under `cover:`.

## Keepsakes: extras/

Scans of the original card, family photos, a letter: pictures that print with
an entry or a chapter. Put the files in an `extras/` folder and list the ones to
print in `extras/extras.md`:

```markdown
# Extras

![Ruth's original card, about 1975](ruth-card.jpg)
![Ruth at the stove, about 1962](ruth-kitchen.jpg)
```

| Folder | Prints with |
|---|---|
| `book/recipes/{chapter}/{slug}/extras/` or `book/sections/{chapter}/{slug}/extras/` | that entry |
| `book/sections/{chapter}/extras/` | the chapter's opening page, or the one-page chapter |

- **Only listed files print**, in the order listed. Each line is
  `![Caption](file)`: the caption prints under the picture, in italics. The
  heading and any other text in `extras.md` are ignored.
- `.jpg` and `.png` only, with no transparency.
- Size, measured on the long edge: at least **700 pixels** for an inset and
  **1500 pixels** for a keepsake page. Scan cards at 300–600 dpi.

Where they print is decided for you:

- **Inset**: up to two items along the foot of the entry's own page, when the
  page has room. Only framed text pages, chapter opening pages, and short
  Half-Page Classic recipes can take one.
- **Keepsake page**: otherwise, a page right after the entry, with each item
  as large as the page allows. Wide items take the full width, and tall ones
  pair side by side, two rows to a page. More items continue onto further
  pages. A recipe on two pages always gets a keepsake page after the second
  page.

To choose, add `extras: inset` or `extras: page` to the entry's row in
`layouts:` ([BOOK-YAML.md](BOOK-YAML.md#layouts)). A card whose handwriting
must be readable belongs on a keepsake page.

Lint reports:

- **Errors**: a listed file that is missing or is not `.jpg`/`.png`, and an
  `extras.md` that lists nothing.
- **Warnings**: files that are not listed (they do not print), an `extras/`
  with no `extras.md`, a missing caption, an image too small for where it
  lands, and transparency.

The studio's **Photos & keepsakes** tab adds and removes keepsakes for you.

## Placeholder text

`cookbook init` fills the pages it cannot write for you with lines that start
`TODO`: the dedication, each chapter's message, the closing message, the back
cover, and the subtitle in `book.yaml`. `cookbook lint` reports every `TODO`
line in `book/` and in `book.yaml` as an error, and `cookbook press` will not
make the print files until they are gone. Replace each one with your own words,
or delete a chapter message you do not want.
