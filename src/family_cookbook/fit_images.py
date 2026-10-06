"""Produce layout-fitted image variants from existing recipe photos — for free.

Tier 0-1 of the "derive, don't regenerate" ladder: for each recipe that has a
photo and an image-bearing layout archetype, crop the existing image to that
archetype's frame aspect ratio and save it beside the original as
`{slug}-{key}.jpg`. render.py then prefers these variants.

The crop window follows the dish: render.py's photo_subject() finds it in
the photo, and subject_crop() tightens a band or column frame around it or
slides the largest window to hold as much of it as the frame allows. A
recipe's `- **Image position:**` overrides that for a photo the detection
misjudges.

No AI, no cost, no upscaling: crops are taken at the source's native
resolution, and a tightened crop never prints below 300 ppi. Two reports
follow the run, and nothing is regenerated here:
  - crops too small for crisp print — candidates for a higher-resolution image;
  - placed frames that break photo_fit()'s rules — a frame that cuts through
    the dish's top or cuts the food, a sidebar the food barely fills, or one
    holding too little of the food. Auto-assignment only places such a frame
    when the recipe's text fits no frame its photo suits (a photo never costs a
    second page), so these are candidates for a regenerated photo; or set the
    recipe's `Image position`.
Existing variants are skipped (cached) while they are newer than their source
photo and were cut with the current frame and crop window.

Usage:
    cookbook fit            # build/update all variants
    cookbook fit --force    # rebuild even if up to date
"""
from __future__ import annotations

from PIL import Image

from . import render

# A crop narrower than this share of the width the frame prints at 300 PPI is
# reported as low-res.
LOW_RES_SHARE = 0.85


def main(force: bool = False) -> None:
    recipes = render.assemble_recipes()

    # Superset of every variant suffix we've ever produced, so cleanup also
    # removes keys retired from PHOTO_FRAMES (e.g. the old "inset", and "half"
    # and "dense" now that bands are framed in the browser).
    all_keys = {"hero", "half", "sidebar", "inset", "dense", "spread", "facing"}
    built = skipped = removed = 0
    low_res: list[str] = []
    cut_dish: list[str] = []
    for r in recipes:
        frame = render.photo_frame(r, r.archetype) if (r.archetype in render.PHOTO_FRAMES and r.has_image) else None
        keep = frame[0] if frame else None

        images_dir = r.folder / "images"

        # cleanup: drop stale variants from a recipe's previous archetype(s)
        for k in all_keys - ({keep} if keep else set()):
            stale = images_dir / f"{r.slug}-{k}.jpg"
            if stale.exists():
                stale.unlink()
                removed += 1

        if not frame:
            continue
        key, win, hin, _ = frame
        box, problem, _ = render.photo_fit(r, r.archetype)
        if problem:
            cut_dish.append(f"{r.category}/{r.slug} [{r.archetype}]: {problem}")
        needed_px = win * render.PRINT_PPI
        if box[2] - box[0] < needed_px * LOW_RES_SHARE:
            low_res.append(
                f"{r.category}/{r.slug} [{r.archetype}]: {box[2] - box[0]}px wide, "
                f"want ~{round(needed_px)}px for {win:g}in @ {render.PRINT_PPI}ppi"
            )
        if not key:
            continue  # a band: FIT_SCRIPT frames the canonical image in the browser
        source = render.master_image(r)
        variant = images_dir / f"{r.slug}-{key}.jpg"

        # The crop depends on the frame and on where the dish was found (or the
        # recipe's `Image position`), none of which lives in the photo's mtime,
        # so each variant is stamped with the window it was cut with and
        # rebuilt when that changes.
        stamp = f"fit-images {win:g}x{hin:g} crop={','.join(map(str, box))}".encode("ascii")
        if variant.exists() and not force and variant.stat().st_mtime >= source.stat().st_mtime:
            with Image.open(variant) as existing:
                current = existing.info.get("comment") == stamp
            if current:
                skipped += 1
                continue

        with Image.open(source) as img:
            out = img.convert("RGB").crop(box)
            out.save(variant, "JPEG", quality=90, comment=stamp)

        built += 1
        print(f"  fitted {variant.relative_to(render.ROOT)}  ({out.width}x{out.height})")

    print(f"\nVariants built: {built}, up-to-date: {skipped}, stale removed: {removed}")
    if low_res:
        print(f"\nLow-res for crisp print ({len(low_res)}) — candidates for a higher-res image:")
        for line in low_res:
            print(f"  - {line}")
    if cut_dish:
        print(f"\nFrame breaks the photo rules ({len(cut_dish)}) — candidates for a regenerated "
              "photo, a layouts: row with a frame that suits it, or an Image position:")
        for line in cut_dish:
            print(f"  - {line}")
