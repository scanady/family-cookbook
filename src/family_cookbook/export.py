"""Export the print HTML to the PDFs uploaded to the printer.

Both the interior and the cover are printed by Playwright's Chromium over CDP
with a streamed `Page.printToPDF` (transferMode=ReturnAsStream + IO.read
chunks): Chrome's `--headless=new --print-to-pdf` CLI path crashes its renderer
on a long book, and the uncompressed interior — hundreds of MB — is too large
for Playwright's `page.pdf()` string transport. Chromium writes each glyph as a
Type3 font built from vector outlines, which satisfies Lulu's "fonts embedded
or converted to outlines" rule (the PDF text is not selectable, which is fine
for print). Ghostscript then recompresses the interior's images to 300 PPI sRGB
JPEG, the file that is uploaded.

Chromium is used, not weasyprint, because the layout relies on CSS print
engines don't fully support — column-count, color-mix, object-fit, and the JS
fit pass that shrinks any overflowing page.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Playwright, sync_playwright

from .config import BookRoot

# The press compression: images to 300 PPI sRGB JPEG, the vendor's resolution
# and color requirements. Visually identical, about a tenth of the size.
GS_PRESS = [
    "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6",
    "-sColorConversionStrategy=sRGB", "-dProcessColorModel=/DeviceRGB",
    "-dAutoFilterColorImages=false", "-dColorImageFilter=/DCTEncode", "-dJPEGQ=90",
    "-dDownsampleColorImages=true", "-dColorImageResolution=300",
    "-dColorImageDownsampleThreshold=1.0",
    "-dDownsampleGrayImages=true", "-dGrayImageResolution=300",
]

MISSING_CHROMIUM = "Chromium for Playwright is not installed — run: python -m playwright install chromium"


def launch_chromium(p: Playwright):
    """Playwright's Chromium, or a clear exit when it was never installed."""
    try:
        return p.chromium.launch()
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            raise SystemExit(MISSING_CHROMIUM) from None
        raise


def _require_input(path: Path, command: str) -> None:
    if not path.is_file():
        raise SystemExit(f"Input not found: {path}\nRun: {command}")


def _report(root: BookRoot, pdf: Path) -> None:
    print(f"Wrote {pdf.relative_to(root.path)}  ({pdf.stat().st_size / 1_048_576:.1f} MB)")


def _ghostscript() -> str:
    gs = shutil.which("gs") or shutil.which("gswin64c")
    if not gs:
        raise SystemExit("Ghostscript (gs) is not installed — it compresses the interior for "
                         "press; install it (e.g. apt install ghostscript, brew install ghostscript)")
    return gs


def require_press_tools() -> None:
    """Exit clearly when Ghostscript or Playwright's Chromium is missing."""
    _ghostscript()
    with sync_playwright() as p:
        launch_chromium(p).close()


def _print_to_pdf(html: Path, pdf: Path) -> None:
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page()
        page.goto(html.resolve().as_uri(), wait_until="networkidle", timeout=300_000)
        page.evaluate("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(8_000)  # let the fit JS finish

        cdp = page.context.new_cdp_session(page)
        result = cdp.send("Page.printToPDF", {
            "preferCSSPageSize": True,
            "printBackground": True,
            "displayHeaderFooter": False,
            "marginTop": 0, "marginBottom": 0, "marginLeft": 0, "marginRight": 0,
            "transferMode": "ReturnAsStream",
        })
        stream = result["stream"]
        with open(pdf, "wb") as f:
            while True:
                chunk = cdp.send("IO.read", {"handle": stream, "size": 8 * 1024 * 1024})
                data = chunk["data"]
                f.write(base64.b64decode(data) if chunk.get("base64Encoded") else data.encode("latin-1"))
                if chunk["eof"]:
                    break
        cdp.send("IO.close", {"handle": stream})
        browser.close()


def export_interior(root: BookRoot) -> None:
    """draft/cookbook-print.html -> cookbook-interior.pdf -> cookbook-interior-press.pdf."""
    html = root.draft / "cookbook-print.html"
    raw = root.draft / "cookbook-interior.pdf"
    press = root.draft / "cookbook-interior-press.pdf"
    _require_input(html, "cookbook build --print")
    gs = _ghostscript()  # before the long export, not after it
    _print_to_pdf(html, raw)
    _report(root, raw)
    press.unlink(missing_ok=True)
    proc = subprocess.run([gs, *GS_PRESS, "-o", str(press), str(raw)], capture_output=True, text=True)
    if proc.returncode != 0 or not press.exists():
        raise SystemExit(f"Ghostscript failed (exit {proc.returncode}).\n{proc.stdout}{proc.stderr}")
    _report(root, press)


def export_cover(root: BookRoot) -> None:
    """draft/cookbook-cover.html -> draft/cookbook-cover.pdf."""
    html = root.draft / "cookbook-cover.html"
    pdf = root.draft / "cookbook-cover.pdf"
    _require_input(html, "cookbook cover")
    _print_to_pdf(html, pdf)
    _report(root, pdf)
