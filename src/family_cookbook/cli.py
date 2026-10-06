"""`cookbook` — build a printed family cookbook from a book root.

Every command works on a book root: the folder holding book/book.yaml, given
by --book or else found at or above the current directory.
The modules that lay the book out read the active root when they are imported,
so each command activates the root first and imports them after.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from . import __version__, config, models


def _root(args: argparse.Namespace) -> config.BookRoot:
    try:
        root = config.find_root(args.book or Path.cwd())
    except config.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    config.activate(root)
    config.load_env(root)
    return root


def _split(value: str) -> list[str]:
    return [s.strip() for s in value.split(",") if s.strip()]


def cmd_init(args: argparse.Namespace) -> int:
    from . import scaffold

    root = (args.book or Path.cwd()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    status = scaffold.main(root, _split(args.categories), _split(args.sections),
                           args.title, args.subtitle, args.edition, args.dry_run)
    if status != 0 or args.dry_run:
        return status
    print()
    scaffold.install_agent_files(root, update=False)
    config.load_env(config.BookRoot(root))
    print("\nThe book is started. Next:\n"
          "  cookbook studio              see the book in your browser and work on it\n"
          "  cookbook ingest card.jpg     add a recipe from a photo or scan of the card\n"
          "  cookbook lint                list the TODO lines that are yours to write\n"
          "  cookbook press               make the two PDFs for the printer")
    if not models.service():
        print(f"\n{models.NO_KEY}", file=sys.stderr)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    _root(args)
    from . import render

    render.main(print_mode=args.print, only=set(_split(args.only)))
    return 0


def cmd_cover(args: argparse.Namespace) -> int:
    _root(args)
    from . import cover

    cover.main()
    return 0


def cmd_fit(args: argparse.Namespace) -> int:
    _root(args)
    from . import fit_images

    fit_images.main(force=args.force)
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    _root(args)
    from . import lint

    return lint.main(errors_only=args.errors, quiet=args.quiet)


def cmd_audit(args: argparse.Namespace) -> int:
    root = _root(args)
    from . import audit

    return audit.main(root, run_check=args.check)


def cmd_check(args: argparse.Namespace) -> int:
    from . import check

    html = args.html or _root(args).draft / "cookbook-print.html"
    return check.main(html, verbose=args.verbose)


def cmd_index(args: argparse.Namespace) -> int:
    _root(args)
    from . import index

    return index.main(check=args.check)


def cmd_export(args: argparse.Namespace) -> int:
    root = _root(args)
    from . import export

    if args.what == "interior":
        export.export_interior(root)
    else:
        export.export_cover(root)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    root = _root(args)
    from . import ingest

    return ingest.main(root, args.files, page_spec=args.pages, chapter=args.chapter, cook=args.cook,
                       title=args.title, model_name=args.model, dry_run=args.dry_run)


def cmd_photo(args: argparse.Namespace) -> int:
    root = _root(args)
    from . import photo

    return photo.main(root, args.slugs, attempts=args.attempts, new_prompt=args.new_prompt,
                      prompt_only=args.prompt_only, model_name=args.model, image_model_name=args.image_model)


def cmd_review(args: argparse.Namespace) -> int:
    root = _root(args)
    from . import review

    if args.report:
        return review.report(root)
    return review.main(root, port=args.port, everything=args.all, open_browser=not args.no_open)


def cmd_studio(args: argparse.Namespace) -> int:
    root = _root(args)
    from . import studio

    return studio.main(root, port=args.port, open_browser=not args.no_open)


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import doctor

    try:
        root = config.find_root(args.book or Path.cwd())
    except config.ConfigError:
        root = None
    if root:
        config.load_env(root)
    return doctor.main(root)


def _step(name: str) -> None:
    print(f"\n== cookbook {name}", flush=True)


def cmd_press(args: argparse.Namespace) -> int:
    """lint -> fit -> build --print -> check -> export interior -> cover -> export cover."""
    root = _root(args)
    from . import press

    try:
        failing = press.run(root, _step)
    except press.LintErrors as exc:
        for line in exc.errors:
            print(f"ERROR  {line}")
        print("\npress stopped before building: fix the errors above, then run cookbook press again",
              file=sys.stderr)
        return 1
    if failing:
        print("\npress stopped: fix the pages above, then run cookbook press again",
              file=sys.stderr)
        return 1
    print(f"\nUpload draft/cookbook-interior-press.pdf and draft/cookbook-cover.pdf to the printer: "
          f"{press.PRINTING_URL}")
    return 0


def cmd_agent_files(args: argparse.Namespace) -> int:
    from . import scaffold

    scaffold.install_agent_files(_root(args).path, update=args.update)
    return 0


# The top-level help lists the commands in these groups, in this order: what a
# newcomer needs first, the advanced steps press runs for them last.
GROUPS = ("Start", "Write and review", "Check", "Print", "Advanced")


def parser() -> argparse.ArgumentParser:
    book = argparse.ArgumentParser(add_help=False)
    book.add_argument("--book", type=Path, metavar="PATH",
                      help="the book's folder (default: the current folder, or the nearest "
                           "folder above it that holds book/book.yaml)")

    p = argparse.ArgumentParser(
        prog="cookbook", usage="%(prog)s [-h] [--version] COMMAND ...",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run `cookbook COMMAND -h` for a command's options.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    # The commands are listed in groups in the description, built below.
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND", help=argparse.SUPPRESS)
    listed: dict[str, list[tuple[str, str]]] = {group: [] for group in GROUPS}

    def add(group: str, name: str, handler, help: str, parents=(book,)) -> argparse.ArgumentParser:
        # No help= here, so argparse does not list the commands in one block of its own.
        sp = sub.add_parser(name, parents=list(parents), description=help)
        sp.set_defaults(handler=handler)
        listed[group].append((name, help))
        return sp

    sp = add("Start", "init", cmd_init,
             "start a new book: book/book.yaml, a folder for each chapter, placeholder pages "
             "to fill in, and the guides AI coding assistants follow", parents=())
    sp.add_argument("--book", type=Path, metavar="PATH",
                    help="folder to create the book in (default: the current folder)")
    sp.add_argument("--categories", default="breakfast,mains,sides,desserts",
                    help="comma-separated recipe chapters, in book order (default: "
                         "breakfast,mains,sides,desserts)")
    sp.add_argument("--sections", default="",
                    help="comma-separated chapters of writing rather than recipes (family "
                         "stories, kitchen tips), in book order")
    sp.add_argument("--title", default="Our Family Cookbook",
                    help="the book's title (default: Our Family Cookbook)")
    sp.add_argument("--subtitle", default="TODO: the family name",
                    help="the line under the title, e.g. \"The Smith Family\" (default: a "
                         "placeholder that cookbook lint flags until you replace it)")
    sp.add_argument("--edition", default="First Edition",
                    help="the edition line on the title page (default: First Edition)")
    sp.add_argument("--dry-run", action="store_true",
                    help="list what would be created, write nothing")

    add("Start", "doctor", cmd_doctor,
        "check this computer can make the book: the browser, Ghostscript, poppler, the AI key, "
        "and the book folder, with the command that fixes each")

    sp = add("Write and review", "ingest", cmd_ingest,
             "type up photos or scans of recipe cards and cookbook pages with an AI model, "
             "into book/recipes/ (word-for-word copy plus a clean recipe.md); without an AI "
             "key, file the pages as one recipe to type up by hand")
    sp.add_argument("files", nargs="+", type=Path, metavar="FILE",
                    help="photos or scans (jpg, png, webp, heic) or PDFs: the pages of one source, in order")
    sp.add_argument("--pages", default="", metavar="PAGES",
                    help="read only these pages of the input, e.g. 3, 3-5, or 1,4-6")
    sp.add_argument("--chapter", default="", help="file every recipe in this chapter (default: the model picks)")
    sp.add_argument("--cook", default="", help="credit every recipe to this person (default: whoever the source names)")
    sp.add_argument("--title", default="",
                    help="without AI: the recipe's title (default: from the first file's name)")
    sp.add_argument("--model", default=models.DEFAULT_MODEL, metavar="MODEL",
                    help=f"the model to read with: a Gemini model, or an OpenRouter id such as "
                         f"vendor/model (default: {models.DEFAULT_MODEL})")
    sp.add_argument("--dry-run", action="store_true",
                    help="print what would be written, write nothing (the model is still called)")

    sp = add("Write and review", "photo", cmd_photo,
             "make a photo of each recipe's finished dish with an AI model, retrying until "
             "it fits the page, into images/{slug}.jpg (needs an AI key)")
    sp.add_argument("slugs", nargs="+", metavar="SLUG",
                    help="recipes to photograph, by folder name (e.g. skillet-cornbread)")
    sp.add_argument("--attempts", type=int, default=3, metavar="N",
                    help="images to try per recipe before giving up (default: 3)")
    sp.add_argument("--new-prompt", action="store_true",
                    help="write a new prompts/{slug}-image-prompt.md even if one exists")
    sp.add_argument("--prompt-only", action="store_true",
                    help="write the prompt file and stop, to edit it before any image is made")
    sp.add_argument("--model", default=models.DEFAULT_MODEL, metavar="MODEL",
                    help=f"the model that writes the prompt and inspects each image: a Gemini model, or an "
                         f"OpenRouter id (default: {models.DEFAULT_MODEL})")
    sp.add_argument("--image-model", default=models.DEFAULT_IMAGE_MODEL, metavar="MODEL",
                    help=f"the model that draws the photo: a Gemini model, or an OpenRouter id "
                         f"(default: {models.DEFAULT_IMAGE_MODEL})")

    sp = add("Write and review", "review", cmd_review,
             "check typed-up recipes against the original cards in your browser, correcting "
             "and approving each")
    sp.add_argument("--all", action="store_true", help="list every recipe, approved ones included")
    sp.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    sp.add_argument("--no-open", action="store_true", help="print the address instead of opening a browser")
    sp.add_argument("--report", action="store_true",
                    help="print review counts and the average time per recipe, and exit")

    sp = add("Write and review", "studio", cmd_studio,
             "work on the whole book in your browser: see the pages, review recipes, reorder "
             "chapters, add keepsakes, and make the print files")
    sp.add_argument("--port", type=int, default=8770, help="local port (default: 8770)")
    sp.add_argument("--no-open", action="store_true", help="print the address instead of opening a browser")

    sp = add("Check", "lint", cmd_lint,
             "find mistakes in the book's files: missing sections, broken links, leftover "
             "placeholder text")
    sp.add_argument("--errors", action="store_true", help="errors only, skip warnings")
    sp.add_argument("--quiet", action="store_true", help="exit code only, no output")

    sp = add("Check", "audit", cmd_audit,
             "read every recipe for content mistakes (times, temperatures, ingredients, lines "
             "left out) and write a report to draft/book-report.html")
    sp.add_argument("--check", action="store_true",
                    help="also measure the print layout (draft/cookbook-print.html) for text "
                         "that overflows or is too small (slower)")

    sp = add("Check", "check", cmd_check,
             "find printed pages where text runs off the page or is smaller than 10 pt")
    sp.add_argument("html", nargs="?", type=Path, metavar="HTML",
                    help="print layout to check (default: draft/cookbook-print.html)")
    sp.add_argument("--verbose", action="store_true",
                    help="also show each failing page's layout and the measurements behind the failure")

    add("Print", "press", cmd_press,
        "make the two PDFs to upload to the printer: the pages and the cover (runs lint, "
        "fit, build --print, check, export, and cover in turn)")

    add("Print", "cover", cmd_cover,
        "lay out the wraparound hardcover cover (back, spine, front) to draft/cookbook-cover.html")

    sp = add("Print", "export", cmd_export, "turn a print layout into a PDF for the printer")
    sp.add_argument("what", choices=("interior", "cover"),
                    help="interior: the pages, draft/cookbook-interior.pdf, compressed to "
                         "cookbook-interior-press.pdf; cover: draft/cookbook-cover.pdf")

    sp = add("Advanced", "build", cmd_build,
             "lay out the book as a web page to look through: draft/cookbook-draft.html")
    sp.add_argument("--print", action="store_true",
                    help="lay out at the printed size instead, with the bleed (the margin the "
                         "printer trims off) and the binding margin: draft/cookbook-print.html")
    sp.add_argument("--only", default="", metavar="SLUGS",
                    help="comma-separated recipe or page folder names to lay out alone, to look at "
                         "a few pages; this replaces draft/cookbook-draft.html with just those "
                         "entries, so run cookbook build again for the whole book")

    sp = add("Advanced", "fit", cmd_fit, "re-crop the recipe photos to fit their page layouts")
    sp.add_argument("--force", action="store_true", help="rebuild even if up to date")

    sp = add("Advanced", "index", cmd_index,
             "rewrite index.md, a clickable list of every recipe and page for the book's repository")
    sp.add_argument("--check", action="store_true", help="exit 1 if index.md is out of date")

    sp = add("Advanced", "agent-files", cmd_agent_files,
             "copy the guides AI coding assistants (Claude Code, Copilot) follow into the book's folder")
    sp.add_argument("--update", action="store_true",
                    help="replace installed copies with this engine version's")

    width = max(len(name) for commands in listed.values() for name, _ in commands)
    p.description = "Make a printed family cookbook from markdown recipes.\n\n" + "\n\n".join(
        f"{group}:\n" + "\n".join(
            "\n".join(textwrap.wrap(help, 79, initial_indent=f"  {name:<{width}}  ",
                                    subsequent_indent=" " * (width + 4),
                                    break_long_words=False, break_on_hyphens=False))
            for name, help in commands)
        for group, commands in listed.items())
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.handler(args)
