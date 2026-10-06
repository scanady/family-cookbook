"""`cookbook doctor`: is this computer ready to make the book?

Each check names what it is for and, when it fails, the one command that fixes
it. Chromium and Ghostscript are required to print; poppler, the AI key, and a
book in this folder are not, so missing them is reported without failing.
"""
from __future__ import annotations

import platform
import shutil
import sys

from . import __version__, config, models
from .export import GHOSTSCRIPT_INSTALL, find_ghostscript
from .ingest import POPPLER_INSTALL


def _chromium_install() -> str:
    # --with-deps adds Chromium's system libraries, which only Linux needs.
    command = "-m playwright install" + (" --with-deps" if sys.platform.startswith("linux") else "") + " chromium"
    if " " not in sys.executable:
        return f"{sys.executable} {command}"
    # PowerShell runs a quoted path only after &.
    return f'& "{sys.executable}" {command}' if sys.platform == "win32" else f'"{sys.executable}" {command}'


def chromium_problem() -> str | None:
    """Why Playwright's Chromium will not start, or None when it does."""
    from playwright.sync_api import Error, sync_playwright

    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Error as exc:
        return str(exc).strip().splitlines()[0]
    return None


def main(root: config.BookRoot | None) -> int:
    chromium = chromium_problem()
    ai = models.service()
    # (ok, required, what it is, the fix)
    checks = [
        (chromium is None, True, "Chromium, which lays out the pages" + (f" ({chromium})" if chromium else ""),
         _chromium_install()),
        (bool(find_ghostscript()), True, "Ghostscript, which makes the print files", GHOSTSCRIPT_INSTALL),
        (bool(shutil.which("pdftoppm")), False, "poppler, which reads PDF files for cookbook ingest",
         POPPLER_INSTALL),
        (bool(ai), False, f"AI, through {ai}" if ai else "AI: no key (without one, ingest and photo work by hand)",
         "paste an OpenRouter key (https://openrouter.ai/keys) after OPENROUTER_API_KEY=, or a Gemini key "
         "(https://aistudio.google.com/apikey) after GEMINI_API_KEY=, in the book's .env"),
        (root is not None, False, f"the book: {root.path}" if root else "a book in this folder",
         "cookbook init"),
    ]
    print(f"cookbook {__version__}, Python {platform.python_version()}")
    for ok, required, what, fix in checks:
        print(f"  {'ok' if ok else 'MISSING' if required else 'off':<8} {what}")
        if not ok:
            print(f"  {'':<8} fix: {fix}")
    if all(ok for ok, required, *_ in checks if required):
        print("\nReady to make the book." if root else "\nReady: start a book here with cookbook init.")
        return 0
    print("\nNot ready to print: run the fix under each MISSING line.")
    return 1
