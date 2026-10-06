"""Render the hardcover casewrap cover wrap for the book.

Lulu HARDCOVER CASEWRAP, US Letter (8.5 x 11 trim). The printed wrap is one
wide sheet that folds over both boards plus the spine:

    total width  = 0.75 turn-in + 8.625 back board + SPINE + 8.625 front board
                   + 0.75 turn-in   = 18.75 + SPINE  (board = 8.5 trim + 0.125 overhang)
    total height = 0.75 turn-in + 11.25 board + 0.75 turn-in = 12.75

SPINE comes from the interior page count, looked up in Lulu's hardcover spine
table (lulu.py). The page count is computed by laying out the book exactly as
render.py does, so the cover can never be built for a stale page count.

Output: draft/cookbook-cover.html — export with `cookbook export cover`.
"""
from __future__ import annotations

import html

from . import config, render
from .lulu import spine_width

# Cover copy and the book's identity come from book/book.yaml, so the cover and
# the title page cannot drift apart. The spine is a vendor measurement derived
# from the page count, so it lives in lulu.py rather than in book.yaml.
BOOK_ROOT = config.active_root()
OUTPUT = BOOK_ROOT.draft / "cookbook-cover.html"
CONFIG = config.load_or_exit(BOOK_ROOT)
_COVER = CONFIG.cover

ACCENT = _COVER.get("accent", "#7E3B3B")
COVER_PHOTO = _COVER.get("photo", "")

TITLE = CONFIG.title
SUBTITLE = CONFIG.subtitle
EDITION = CONFIG.edition
SPINE_TEXT = _COVER.get("spine_text", f"{CONFIG.title} · {CONFIG.subtitle}")

# The back-cover prose is content, so it lives in book/cover.md rather than in
# book.yaml next to the accent and the photo path. Escaped here because it is
# authored as plain markdown text, not as pre-escaped HTML.
_blurb, _signoff = config.load_cover_copy(BOOK_ROOT)
BACK_BLURB = html.escape(_blurb)
BACK_SIGNOFF = html.escape(_signoff)

# --- geometry (inches) -------------------------------------------------------
TURN_IN = 0.75
TRIM_W, TRIM_H = 8.5, 11.0
OVERHANG = 0.125
BOARD_W = TRIM_W + OVERHANG          # 8.625
BOARD_H = TRIM_H + 2 * OVERHANG      # 11.25
TOTAL_H = 2 * TURN_IN + BOARD_H      # 12.75; width depends on the spine
SAFE = 0.5                           # Lulu safety inside trim
HINGE = 0.25                         # keep art off the spine hinge


def interior_page_count() -> int:
    """Pages in the bound interior. The screen and print builds paginate
    identically (recto openers, blanks, two-page pairs), so laying the book
    out here gives the count Lulu will see."""
    _, shown = render.build(render.assemble_recipes())
    return len(shown)


def build(fonts: str, spine_in: float) -> str:
    total_w = 2 * TURN_IN + 2 * BOARD_W + spine_in
    # A book without a cover photo keeps the frame's room, so the title and
    # edition stay where they are, but prints no empty box.
    frame = (f'<div class="frame"><img src="../book/recipes/{COVER_PHOTO}" alt=""></div>'
             if COVER_PHOTO else '<div class="frame frame--empty"></div>')
    css = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: #d9d4cc; }}
:root {{ --paper:#faf7f1; --ink:#2c2723; --muted:#6b6259; --accent:{ACCENT}; }}
@page {{ size: {total_w}in {TOTAL_H}in; margin: 0; }}
.wrap {{
  position: relative; width: {total_w}in; height: {TOTAL_H}in; background: var(--paper);
  overflow: hidden; print-color-adjust: exact; -webkit-print-color-adjust: exact;
  font-family: 'Source Sans 3', Arial, sans-serif; color: var(--ink);
}}
/* Board panels (front/back) and spine, positioned across the flat wrap. */
.panel {{ position: absolute; top: {TURN_IN}in; height: {BOARD_H}in; }}
.back  {{ left: {TURN_IN}in; width: {BOARD_W}in; }}
.spine {{ left: {TURN_IN + BOARD_W}in; width: {spine_in}in; }}
.front {{ left: {TURN_IN + BOARD_W + spine_in}in; width: {BOARD_W}in; }}

/* Front cover content, inset to the safe area (away from outer trim + hinge). */
.front-in {{
  position: absolute; inset: {SAFE}in {SAFE}in {SAFE}in {HINGE + 0.25}in;
  display: flex; flex-direction: column; align-items: center; text-align: center;
}}
.title {{ font-family: 'Playfair Display', Georgia, serif; font-weight: 800;
  font-size: 42pt; line-height: 1.02; margin-top: 0.15in; }}
.subtitle {{ font-family: 'Playfair Display', Georgia, serif; font-style: italic;
  font-weight: 500; font-size: 20pt; color: var(--muted); margin-top: 8pt; }}
.frame {{ margin: 0.32in 0; width: 100%; flex: 1; min-height: 0; border: 3pt solid var(--accent);
  padding: 7pt; background: #fff; }}
.frame img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.frame--empty {{ border: 0; background: none; }}
.edition {{ font-size: 12pt; letter-spacing: .22em; text-transform: uppercase;
  color: var(--accent); font-weight: 700; margin-bottom: 0.1in; }}
.rule {{ height: 2.5px; width: 1.6in; background: var(--accent); margin: 10pt auto; }}

/* Spine — rotated title, centered; small enough to stay off the hinge folds. */
.spine-in {{ position: absolute; inset: {SAFE}in 0; display: flex;
  align-items: center; justify-content: center; }}
.spine-txt {{ transform: rotate(90deg); transform-origin: center; white-space: nowrap;
  font-family: 'Playfair Display', Georgia, serif; font-weight: 700; font-size: 11pt;
  color: var(--ink); letter-spacing: .02em; }}

/* Back cover — blurb centered in the safe area. */
.back-in {{ position: absolute; inset: {SAFE}in {HINGE + 0.25}in {SAFE}in {SAFE}in;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; }}
.back-title {{ font-family: 'Playfair Display', Georgia, serif; font-weight: 700;
  font-size: 17pt; color: var(--accent); margin-bottom: 14pt; }}
.blurb {{ font-size: 12.5pt; line-height: 1.6; max-width: 4.6in; color: var(--ink); }}
.signoff {{ font-family: 'Playfair Display', Georgia, serif; font-style: italic;
  font-size: 12pt; color: var(--muted); margin-top: 18pt; }}

/* Faint guide lines (screen only) marking trim/spine folds — hidden in print. */
.guide {{ position: absolute; top: 0; bottom: 0; width: 0; border-left: 0.5pt dashed rgba(126,59,59,.4); }}
@media print {{ .guide {{ display: none; }} }}
"""
    guides = "".join(
        f'<div class="guide" style="left:{x}in"></div>'
        for x in (
            TURN_IN, TURN_IN + BOARD_W, TURN_IN + BOARD_W + spine_in, TURN_IN + 2 * BOARD_W + spine_in,
        )
    )
    body = f"""
<div class="wrap">
  {guides}
  <div class="panel back">
    <div class="back-in">
      <div class="back-title">{TITLE}</div>
      <p class="blurb">{BACK_BLURB}</p>
      <div class="rule"></div>
      <p class="signoff">{BACK_SIGNOFF}</p>
    </div>
  </div>
  <div class="panel spine">
    <div class="spine-in"><div class="spine-txt">{SPINE_TEXT}</div></div>
  </div>
  <div class="panel front">
    <div class="front-in">
      <div class="title">{TITLE}</div>
      <div class="subtitle">{SUBTITLE}</div>
      {frame}
      <div class="rule"></div>
      <div class="edition">{EDITION}</div>
    </div>
  </div>
</div>
"""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{html.escape(TITLE)} — Cover</title>"
        f"<style>{fonts}{css}</style></head><body>{body}</body></html>"
    )


def main() -> None:
    pages = interior_page_count()
    spine_in = spine_width(pages)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build(render.font_face_css(), spine_in), encoding="utf-8", newline="\n")
    total_w = 2 * TURN_IN + 2 * BOARD_W + spine_in
    print(f"Wrote {OUTPUT.relative_to(BOOK_ROOT.path)}")
    print(f"Casewrap: {total_w:.3f} x {TOTAL_H:.3f} in  (spine {spine_in} in for {pages} pages, Lulu hardcover table)")

