"""`cookbook photo`: a dish photograph the book's layouts can use.

For each recipe:

1. The prompt. prompts/{slug}-image-prompt.md when it exists, since a person
   may have written or tuned it; otherwise a text model fills in the image
   skill's prompt template from recipe.md, and the result is saved there.
2. A candidate. The image model draws it at 3:4 and 4K; the engine cuts it to
   the 8:11 master and keeps it in draft/photos/{slug}/.
3. Two judgements. The engine's own: render.photo_fit() for every photo layout
   the recipe's text can take, the same test the build uses to place a photo,
   so a candidate passes only if the build will give it a layout without
   `cookbook fit` flagging it. And a vision model's: visible text, an extra
   dish, a vessel cut by the edge, a dish that does not match the recipe.
4. Accept or correct. The first candidate that passes both becomes
   images/{slug}.jpg (a photo it replaces is kept beside the candidates). A
   failing one is followed by another with a measured correction added to the
   prompt: where the dish landed, and where it has to go.

The prompt that produced the accepted photo is the one saved, corrections
included, so the photo can be made again.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import shutil
from importlib import resources
from pathlib import Path

from PIL import Image

from . import config, models

ASPECT = "3:4"          # the generator's nearest ratio to the 8:11 page
SIZE = "4K"             # 3584 x 4800 at 3:4; never the ~1K default
PRINT_MIN = (2400, 3300)  # 8 x 11 in at 300 PPI
MASTER_RATIO = 8 / 11

PROMPT_WRITER = """\
You are a cookbook art director writing the brief for one photograph of a
finished recipe. Fill in the prompt template below for the recipe that follows
it: replace every [bracketed instruction] with direction specific to this
recipe and remove the brackets. In MANDATORY COMPOSITION keep only the
paragraph for this dish's subject shape. Keep the rest of the template's
wording.

How to read the recipe and style the dish:

{styling}

The composition the book's layouts need:

{composition}

The template:

{template}

The recipe:

{recipe}

Return the subject shape ("plated" or "standing") and the finished prompt.
"""

PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "enum": ["plated", "standing"]},
        "prompt": {"type": "string"},
    },
    "required": ["subject", "prompt"],
}

INSPECT_PROMPT = """\
You are checking a generated photograph for a printed family cookbook against
the recipe it illustrates. Reject it only for a real problem a careful art
director would send back:

- any visible text, letters, numbers, logo, label, or watermark
- more than one dish, or duplicated servings the recipe does not make
- the food or its vessel cut off by an edge of the image
- a dish that does not look like this recipe: the wrong form, ingredients or
  garnish the recipe does not have, the wrong color or texture
- malformed, melted, or impossible objects; food that looks fake or plastic

The recipe:

{recipe}
"""

INSPECT_SCHEMA = {
    "type": "object",
    "properties": {
        "acceptable": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["acceptable", "problems"],
}

# Where each subject shape has to sit, as the skill states it; the correction
# after a rejected candidate repeats it with the measured miss.
TARGET = {
    "plated": "low and wide: the whole arrangement, top of the food to the rim of the vessel, "
              "between about 40 and 70 percent of the frame height measured from the top, no taller "
              "than a quarter of the frame, centred and spanning about 75 to 85 percent of the width",
    "standing": "upright and centred in the middle half of the width, its full height from base to "
                "top spanning about 25 to 80 percent of the frame height",
}


def _skill() -> str:
    return (resources.files("family_cookbook") / "agent_files" / "skills" /
            "design-visual-cookbook-image-generator" / "SKILL.md").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    match = re.search(rf"{re.escape(start)}(.*?){re.escape(end)}", text, flags=re.S)
    if not match:
        raise SystemExit(f"the image skill has no '{start}' section — reinstall the engine")
    return match.group(1).strip()


def recipe_text(r) -> str:
    """recipe.md without its photo line and source link: the dish, nothing else."""
    lines = (r.folder / "recipe.md").read_text(encoding="utf-8").splitlines()
    return "\n".join(l for l in lines if not l.startswith("![") and not l.startswith("[View")).strip()


def write_prompt(model: models.Model, r) -> tuple[str, models.Usage]:
    skill = _skill()
    template = _between(skill, "```text\n", "```")
    answer, usage = model.json(PROMPT_WRITER.format(
        styling=_between(skill, "### Step 1: Read the Recipe as Visual Evidence", "### Step 3"),
        composition=_between(skill, "Choose the composition by the subject's shape:", "Keep critical food details"),
        template=template,
        recipe=recipe_text(r),
    ), PROMPT_SCHEMA)
    prompt = answer["prompt"].strip()
    # Models sometimes return the brief as one line: put each of the template's
    # section headings ("IMAGE GOAL:") back on a line of its own.
    for heading in re.findall(r"^([A-Z][A-Z ,-]+:)$", template, flags=re.M):
        prompt = re.sub(rf"\s*{re.escape(heading)}\s*", f"\n\n{heading}\n", prompt)
    prompt = prompt.strip()
    prompt += ("\n\nRECIPE SOURCE OF TRUTH:\nUse only the finished dish, ingredients, preparation, serving "
               "instructions, and garnish the recipe below supports.\n\n" + recipe_text(r))
    return prompt + "\n", usage


def to_master(data: bytes, dest: Path) -> tuple[int, int]:
    """The generated image cut to the 8:11 master, centred, saved as a 300 PPI JPEG."""
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        w, h = img.size
        if w / h > MASTER_RATIO:
            cw = round(h * MASTER_RATIO)
            img = img.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
        else:
            ch = round(w / MASTER_RATIO)
            img = img.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch))
        img.save(dest, "JPEG", quality=92, dpi=(300, 300))
        return img.size


def layouts_for(render, r) -> list[str]:
    """The photo layouts the build could give r, by its text: the one-page
    rotation's, else the Two-Page Spread's full-page photo."""
    one_page = [a for a in dict.fromkeys(a for a, _ in render.IMG_ROTATION) if render.holds_at_full_type(r, a)]
    if one_page:
        return one_page
    spread = render.TWO_PAGE_SPREAD[0]
    return [spread] if render.holds_at_full_type(r, spread) else []


def correction(render, candidate: Path, shape: str, layout_problems: list[str], looks: list[str]) -> str:
    s = render.photo_subject(candidate)
    x0, y0, x1, y1 = s.box
    lines = ["CORRECTION AFTER THE PREVIOUS ATTEMPT:"]
    if layout_problems:
        lines.append(
            f"The food spanned {y0:.0%} to {y1:.0%} of the frame height and {x0:.0%} to {x1:.0%} of its "
            f"width, and the page layouts could not use it ({'; '.join(layout_problems)}). "
            f"Compose the subject {TARGET[shape]}."
        )
    if looks:
        lines.append("Also fix: " + "; ".join(looks) + ".")
    return "\n".join(lines)


def link_photo(r) -> None:
    """Add the photo line recipe.md needs, before its metadata, if it has none."""
    md = r.folder / "recipe.md"
    lines = md.read_text(encoding="utf-8").splitlines()
    link = f"images/{r.slug}.jpg"
    if any(link in l for l in lines):
        return
    at = next((i for i, l in enumerate(lines) if l.startswith("- **") or l.startswith("## ")), len(lines))
    lines[at:at] = [f"![{r.title}]({link})", ""]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make(root: config.BookRoot, render, r, *, attempts: int, new_prompt: bool, prompt_only: bool,
         text_model: models.Model, image_model) -> tuple[bool, models.Usage]:
    spent = models.NO_USAGE
    prompt_file = r.folder / "prompts" / f"{r.slug}-image-prompt.md"
    if prompt_file.exists() and not new_prompt:
        prompt = prompt_file.read_text(encoding="utf-8")
        print(f"  prompt: {prompt_file.relative_to(root.path)}")
    else:
        try:
            prompt, usage = write_prompt(text_model, r)
        except models.Refused as exc:
            raise SystemExit(f"{r.slug}: {exc} — write prompts/{r.slug}-image-prompt.md by hand") from None
        spent += usage
        prompt_file.parent.mkdir(exist_ok=True)
        prompt_file.write_text(prompt, encoding="utf-8")
        print(f"  prompt written: {prompt_file.relative_to(root.path)}")
    if prompt_only:
        return True, spent

    layouts = layouts_for(render, r)
    out = root.draft / "photos" / r.slug
    out.mkdir(parents=True, exist_ok=True)
    first = 1 + max((int(m.group(1)) for p in out.glob("candidate-*.jpg")
                     if (m := re.fullmatch(r"candidate-(\d+)\.jpg", p.name))), default=0)
    attempt_prompt = prompt
    for n in range(first, first + attempts):
        try:
            data, usage = image_model.image(attempt_prompt, ASPECT, SIZE)
        except models.Refused as exc:
            print(f"  attempt {n}: {exc}")
            continue
        spent += usage
        candidate = out / f"candidate-{n}.jpg"
        size = to_master(data, candidate)
        print(f"  {candidate.relative_to(root.path)}  {size[0]}x{size[1]}", end="")
        if size[0] < PRINT_MIN[0] or size[1] < PRINT_MIN[1]:
            print(f"  — below print resolution {PRINT_MIN[0]}x{PRINT_MIN[1]}")
            continue
        fits = {a: render.photo_fit(r, a, candidate) for a in layouts}
        taken = [a for a, f in fits.items() if not f.problem]
        try:
            looks, usage = text_model.json(INSPECT_PROMPT.format(recipe=recipe_text(r)), INSPECT_SCHEMA, [candidate])
        except models.Refused as exc:
            looks, usage = {"acceptable": False, "problems": [f"the check could not run ({exc})"]}, models.NO_USAGE
        spent += usage
        flaws = [] if looks["acceptable"] else [p for p in looks["problems"] if p.strip()]
        if (taken or not layouts) and not flaws:
            print(f"  — accepted ({', '.join(taken) or 'no fixed frame: the Recipe Spread flows around it'})")
            master = r.folder / "images" / f"{r.slug}.jpg"
            master.parent.mkdir(exist_ok=True)
            if master.exists():
                kept = out / f"previous-{dt.datetime.now():%Y%m%d-%H%M%S}.jpg"
                shutil.move(master, kept)
                print(f"  the photo it replaces: {kept.relative_to(root.path)}")
            shutil.copyfile(candidate, master)
            if attempt_prompt != prompt or not prompt_file.exists():
                prompt_file.write_text(attempt_prompt, encoding="utf-8")
            link_photo(r)
            return True, spent
        problems = [f"{a}: {f.problem}" for a, f in fits.items()] if not taken else []
        print("  — " + "; ".join(problems + flaws))
        s = render.photo_subject(candidate)
        shape = "standing" if (s.box[3] - s.box[1]) * 11 > (s.box[2] - s.box[0]) * 8 else "plated"
        attempt_prompt = prompt.rstrip() + "\n\n" + correction(render, candidate, shape, problems, flaws) + "\n"
    print(f"  no candidate passed in {attempts} attempt(s); all kept in {out.relative_to(root.path)}/ "
          "— pick one by eye and copy it to images/, or edit the prompt and run again")
    return False, spent


def main(root: config.BookRoot, slugs: list[str], *, attempts: int = 3, new_prompt: bool = False,
         prompt_only: bool = False, model_name: str = models.DEFAULT_MODEL,
         image_model_name: str = models.DEFAULT_IMAGE_MODEL) -> int:
    from . import render  # reads the active root at import

    recipes = {r.slug: r for r in render.assemble_recipes()
               if not (r.is_generated or r.is_divider or r.is_chapter_page) and (r.folder / "recipe.md").exists()}
    missing = [s for s in slugs if s not in recipes]
    if missing:
        raise SystemExit(f"no recipe with slug {', '.join(missing)} in book/recipes/")
    text_model = models.load(model_name)
    image_model = None if prompt_only else models.load(image_model_name)

    failed = 0
    total = models.NO_USAGE
    for slug in slugs:
        r = recipes[slug]
        print(f"\n{r.title} ({r.category}/{slug})")
        ok, spent = make(root, render, r, attempts=attempts, new_prompt=new_prompt, prompt_only=prompt_only,
                         text_model=text_model, image_model=image_model)
        failed += not ok
        total += spent
        models.log(root.book, {
            "command": "photo", "entry": f"recipes/{r.category}/{slug}", "accepted": ok,
            "model": image_model_name if image_model else model_name, **spent.record(),
        })
        print(f"  {'$' + format(spent.cost_usd, '.3f') if spent.cost_usd is not None else 'cost unknown'}")

    if not prompt_only:
        accepted = [s for s in slugs if (recipes[s].folder / "images" / f"{s}.jpg").exists()]
        if accepted:
            print(f"\nNext: cookbook fit, then cookbook build --only {','.join(accepted)} and look at each page.")
    cost = "cost unknown" if total.cost_usd is None else f"${total.cost_usd:.3f}"
    print(f"{len(slugs) - failed} of {len(slugs)} done; {cost}")
    return 1 if failed else 0
