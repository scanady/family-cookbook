# book.yaml reference

`book/book.yaml` holds everything a book decides about itself: its title, its
colors, its chapters and their order, and any page layouts you choose by hand.
`cookbook init` writes one with comments; this page explains every key.

Two rules shape the file:

- **Values, not writing.** Colors, names, order, and file paths go here. Prose
  someone wrote, even one sentence, goes in a markdown file: the back cover in
  `book/cover.md`, a chapter's opening message in `book/sections/{chapter}/page.md`.
- **The chapters list is the book.** Chapters print in the order they are
  listed, front and back matter included.

Page size, margins, fonts, and the layout rotation are not settings. They are
built to the printer's specification ([PRINTING.md](PRINTING.md)) and checked
by `cookbook check`.

How problems are reported:

- **Load error**: every command stops with `error: book.yaml: …` and exit code 2.
- **Lint error / warning**: `cookbook lint` reports it. Errors exit 1 and stop
  `cookbook press`; warnings never fail.

## A complete example

```yaml
book:
  title: "Our Family Cookbook"          # title page, cover, spine
  subtitle: "The Smith Family"          # line under the title
  edition: "First Edition"              # small line on the title page and cover

style:
  default_accent: "#3F3A34"             # any chapter without its own accent

cover:
  spine_text: "Our Family Cookbook · The Smith Family"
  accent: "#7E3B3B"                     # cover frame, rules, and edition line
  photo: "mains/skillet-cornbread/images/skillet-cornbread.jpg"   # under book/recipes/

audit:
  estimates: false                      # true: accept "About …" yields and prep times

chapters:
  - name: title-page                    # generated: built from book: above
    kind: generated
    label: "Title Page"
    toc: false
  - name: matter-dedication             # a one-page chapter
    kind: prose
    label: "Dedication"
    divider: false
  - name: table-of-contents
    kind: generated
    label: "Contents"
    toc: false
  - name: breakfast                     # a recipe chapter
    kind: recipes
    label: "Breakfast"
    accent: "#7E3B3B"
  - name: mains
    kind: recipes
    label: "Mains"
    accent: "#4E6E87"
    pinned: [skillet-cornbread]         # printed first; the rest A–Z
  - name: kitchen-tips                  # a prose chapter
    kind: prose
    label: "Kitchen Tips"
    accent: "#5C6B4E"
  - name: matter-closing-message
    kind: prose
    label: "Closing Message"
    divider: false
  - name: contributors
    kind: generated
    label: "Contributors"
  - name: index                         # optional; leave it out to skip the index
    kind: generated
    label: "Index"

layouts:
  - chapter: mains
    slug: skillet-cornbread
    archetype: Hero Full-Bleed          # see LAYOUTS.md
  - chapter: breakfast
    slug: buttermilk-pancakes
    archetype: Half-Page Classic
    zone: lower-half                    # photo at the foot of the page
    extras: page                        # keepsakes on their own page
```

## `book`

| Key | Type | Default | What it does |
|---|---|---|---|
| `title` | text | `Family Cookbook` | The title on the generated title page, the front cover, and the spine. `cookbook init --title` sets it (init's default: `Our Family Cookbook`). |
| `subtitle` | text | empty | The line under the title on the title page and cover. `cookbook init` writes a `TODO` placeholder unless you pass `--subtitle`; lint reports it as an error until you replace it. |
| `edition` | text | empty | A small line on the title page and the front cover, such as `First Edition` or `Christmas 2026`. |

## `style`

| Key | Type | Default | What it does |
|---|---|---|---|
| `default_accent` | `#RRGGBB` color | `#3F3A34` | The accent color of any chapter that does not set its own. |

## `cover`

| Key | Type | Default | What it does |
|---|---|---|---|
| `spine_text` | text | `{title} · {subtitle}` | The words printed along the spine. Keep it short: a thin book has a narrow spine. |
| `accent` | `#RRGGBB` color | `#7E3B3B` | The cover's frame, rules, and edition line. |
| `photo` | path | none | The front-cover photo, **relative to `book/recipes/`**, for example `desserts/apple-pie/images/apple-pie.jpg`. It is cropped to fill the frame. Without one, the front cover prints the title with no picture. Lint error if the file does not exist. |

The back-cover blurb and sign-off are not keys: they are prose in
`book/cover.md` (see [RECIPE-FORMAT.md](RECIPE-FORMAT.md#the-back-cover-bookcovermd)).
A `back_blurb` or `back_signoff` key here is a lint error.

## `audit`

| Key | Type | Default | What it does |
|---|---|---|---|
| `estimates` | `true` / `false` | `false` | `cookbook audit` flags a Yield or Prep time the recipe's original does not state. Set `true` if your family writes its own estimates as `About …`, and the audit accepts them. Cook time, Temperature, and ingredient amounts are always checked. Load error if it is not `true` or `false`. |

## `chapters`

A list. Each item is one chapter, and the list order is the print order.

| Key | Type | Default | What it does |
|---|---|---|---|
| `name` | text, lowercase-kebab-case | **required** | The chapter's folder name: `book/recipes/{name}/` for recipes, `book/sections/{name}/` for prose. Load error if missing or used twice. |
| `kind` | `recipes`, `prose`, or `generated` | `recipes` | `recipes`: entries are `book/recipes/{name}/{slug}/recipe.md`. `prose`: entries are `book/sections/{name}/{slug}/page.md`. `generated`: a page the engine builds (below). Load error for any other value. |
| `label` | text | the name in Title Case (`kitchen-tips` → `Kitchen Tips`) | The chapter's heading, on its opening page and in the contents. |
| `accent` | `#RRGGBB` color | `style.default_accent` | The chapter's rules, headings, and opening page. Lint error if it is not a six-digit hex color. Adjacent chapters read best with different accents; muted colors print better than bright screen colors. |
| `divider` | `true` / `false` | `true` (`false` for generated chapters) | `true`: the chapter opens with a divider page on a right-hand page, showing its label and the message in `book/sections/{name}/page.md` if there is one. `false`: no divider. A `divider: false` chapter whose folder holds a `page.md` is a **one-page chapter**, such as a dedication: that page prints in the flow. |
| `toc` | `true` / `false` | `true` | `false` leaves the chapter out of the table of contents. |
| `pinned` | list of slugs | none | Entries printed first, in this order. Everything else in the chapter follows alphabetically. There is no way to pin an entry last. |

Load errors you may meet:

- `order` was renamed to `pinned`.
- A generated chapter takes no `divider: true` and no `pinned`.
- A non-generated chapter may not use a generated chapter's name.

Lint also reports:

- **Error**: a recipe or prose chapter whose folder does not exist.
- **Warning**: a chapter with no entries. It would print an opening page and
  nothing after it.
- **Warning**: a folder under `book/recipes/` or `book/sections/` that the list
  does not name. It still prints, at the end of the book.
- **Error**: entries under the wrong base, such as recipes in a `kind: prose`
  chapter.

### Generated chapters

Four pages are built by the engine, never written by hand. Each is a chapter
with `kind: generated` and one of these names. Its place in the list is where
it prints; its `label` is its heading. Leave one out of the list and it does
not print.

| Name | Built from |
|---|---|
| `title-page` | `book.title`, `book.subtitle`, `book.edition` |
| `table-of-contents` | the finished page order (chapters with `toc: true`) |
| `contributors` | every entry's attribution line: each cook, by surname, with their dishes and pages |
| `index` | every entry's title and attribution, A–Z. Optional; `cookbook init` writes it commented out. |

A folder or entry anywhere in `book/` with one of these names is a lint error.

### Front and back matter

A dedication and a closing message are ordinary one-page chapters:
`kind: prose`, `divider: false`, and a `page.md` at
`book/sections/{name}/page.md`. `cookbook init` creates
`matter-dedication` and `matter-closing-message`; the `matter-` prefix only
keeps them together in a folder listing.

## `layouts`

A list of layouts you choose by hand. Anything not listed gets its layout
automatically when the book is built. [LAYOUTS.md](LAYOUTS.md) shows each
layout and how the automatic choice works.

| Key | Type | Default | What it does |
|---|---|---|---|
| `chapter` | chapter name | **required** | The entry's chapter. |
| `slug` | entry folder name | **required** | The entry. Lint error if no such entry exists (often a leftover after a rename). |
| `archetype` | layout name | **required** | One of `Hero Full-Bleed`, `Half-Page Classic`, `Sidebar Portrait`, `Text-Only Framed`, `Inset Original`, `Two-Page Spread`, `Recipe Spread`. Lint error for any other name. |
| `zone` | text | empty | Where the photo sits. Only some words matter: for `Half-Page Classic`, a zone containing `upper` puts the photo above the title and `lower` puts it at the foot of the page; anything else puts it between the title and the recipe. For `Sidebar Portrait`, a zone containing `left` puts the photo on the left; otherwise it is on the right. Other layouts ignore it. |
| `extras` | `inset` or `page` | decided by room | Where the entry's keepsakes print: `inset` along the foot of its own page, `page` on a keepsake page right after it. Load error for any other value. `inset` is ignored (lint warns) on a layout that cannot take one. |
| `spec` | path from the book root | none | An optional notes file describing the layout, for people. Lint error if the path does not exist. |

Lint also reports a duplicate row (error). Other keys in a row, such as a
`note:` for yourself, are ignored.

Rows apply to **entries**: recipes and prose entries. A chapter's opening page
always uses the framed text page, and a one-page chapter (the dedication, the
closing message) is always laid out automatically.

## Other keys

Keys outside `book`, `style`, `cover`, `audit`, `chapters`, and `layouts` are
not read. `cookbook lint` warns about them, so a typo or a block left over from
an older engine (such as `print:`) does not go unnoticed.
