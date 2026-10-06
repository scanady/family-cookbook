"""The press sequence: lint -> fit -> build --print -> check -> export interior
-> cover -> export cover.

`cookbook press` and the studio's "Make the print files" both run it, so the
two can never drift apart. The caller activates the book root first: the
layout modules read it when they are imported.
"""
from __future__ import annotations

from typing import Callable

from . import __version__, config

# The print specification and upload steps, at the installed version's tag.
PRINTING_URL = f"https://github.com/scanady/family-cookbook/blob/v{__version__}/docs/PRINTING.md"


class LintErrors(Exception):
    """`cookbook lint` found errors, so the press stopped before building anything."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"{len(errors)} lint error(s)")
        self.errors = errors


def run(root: config.BookRoot, step: Callable[[str], None]) -> list[dict]:
    """Run the sequence, calling step(name) as each stage begins. Raises
    LintErrors when lint finds any, before anything is built. Returns the
    pages `cookbook check` fails, having stopped there, or [] once both press
    PDFs are written."""
    from . import check, cover, export, fit_images, lint, render

    # A placeholder or a missing page prints as faithfully as the real thing.
    step("lint")
    errors = lint.collect().errors
    if errors:
        raise LintErrors(errors)
    export.require_press_tools()  # before minutes of work, not after
    step("fit")
    fit_images.main()
    step("build --print")
    render.main(print_mode=True)
    step("check")
    failing = check.failing_pages(root.draft / "cookbook-print.html")
    if check.report(failing):
        return failing
    step("export interior")
    export.export_interior(root)
    step("cover")
    cover.main()
    step("export cover")
    export.export_cover(root)
    return []
