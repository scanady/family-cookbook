"""`cookbook studio`: every step of making the book on one local web page.

For whoever makes the book without a terminal. Six tabs, in plain words:

- Book       the screen draft in spreads, and a button that rebuilds it
- Recipes    every recipe by chapter with what the book report finds in it;
             selecting one opens `cookbook review`'s editor beside the original
- Chapters   the order of the chapters, and of the entries in each
- Keepsakes  card scans and family photos printed with an entry (its extras/)
- Report     `cookbook audit`'s book report
- Proof      `cookbook press`, then the two press PDFs a printer needs

Like `cookbook review` it is standard library only, listens on 127.0.0.1 alone,
and serves one self-contained page over a small JSON API. The review editor is
review.py's own page and endpoints, served here unchanged.

book.yaml is written by hand and commented throughout, so reordering edits its
text instead of re-dumping parsed YAML: a chapter's block moves with the
comment lines directly above it, and only its `pinned:` line is replaced or
added. A write stands only if the file then parses to exactly the change asked
for and config.load accepts it; otherwise the old text goes back.

Rebuilding, the report, and the print files run one at a time, each in a fresh
Python process: render.py, cover.py, and fit_images.py read book.yaml when they
are imported, and the studio changes book.yaml while it runs.
"""
from __future__ import annotations

import copy
import json
import mimetypes
import multiprocessing
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import yaml

from . import config, press, review

MAX_UPLOAD = 25 * 1024 * 1024
DRAFT_TYPES = {".html", ".pdf", *review.IMAGE_TYPES}
# A keepsake prints as JPG or PNG, known by its first bytes rather than the name a phone gave it.
PICTURE_TYPES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png"}
JOBS = {"build": "Rebuilding the book", "report": "Checking the book", "proof": "Making the print files"}
STOPPED = "It stopped before finishing; the terminal running cookbook studio says why."


class Problem(Exception):
    """Something the person can act on; the page shows the message as it is."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


# -- book.yaml, edited as text ------------------------------------------------

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _chapter_blocks(lines: list[str]) -> list[tuple[int, int, int]]:
    """Each item of book.yaml's chapters list as (start, dash, end) line indexes:
    its block runs from the comment lines directly above its `- ` line through
    its last indented line. Blank lines and other comments between blocks are
    not part of any block, so they stay where they are when blocks move; so do
    comments right under `chapters:`, which speak for the whole list."""
    head = next((i for i, line in enumerate(lines) if re.match(r"chapters:\s*(#.*)?$", line)), None)
    if head is None:
        raise config.ConfigError("there is no `chapters:` list, one `- name:` block per chapter")
    end = next((i for i in range(head + 1, len(lines)) if re.match(r"[^\s#]", lines[i])), len(lines))
    dashes = [i for i in range(head + 1, end) if re.match(r"\s*-(\s|$)", lines[i])]
    if not dashes:
        raise config.ConfigError("the chapters list is not one `- name:` block per chapter")
    depth = min(_indent(lines[i]) for i in dashes)
    dashes = [i for i in dashes if _indent(lines[i]) == depth]
    blocks, floor = [], head + 1
    for k, dash in enumerate(dashes):
        stop = dashes[k + 1] if k + 1 < len(dashes) else end
        last = dash
        for j in range(dash + 1, stop):
            if lines[j].strip():
                if _indent(lines[j]) <= depth:
                    break
                last = j
        start = dash
        while start > floor and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        if start == head + 1:
            start = dash
        blocks.append((start, dash, last + 1))
        floor = last + 1
    return blocks


def _yaml_text(root: config.BookRoot) -> tuple[list[str], dict]:
    text = root.config_path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"  # so the last block can move up and still end its line
    return text.splitlines(keepends=True), yaml.safe_load(text) or {}


def _write_checked(root: config.BookRoot, lines: list[str], expected: dict) -> None:
    """Write book.yaml, keeping it only if it parses to `expected` and config.load accepts it."""
    text = "".join(lines)
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        parsed = None
    if parsed != expected:
        raise config.ConfigError("the studio could not make this change to the file's text safely; "
                                 "make it by hand in book/book.yaml")
    path = root.config_path
    before = path.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    try:
        config.load(root)
    except config.ConfigError:
        path.write_text(before, encoding="utf-8")
        raise


def reorder_chapters(root: config.BookRoot, order: list[str]) -> None:
    """Rewrite book.yaml so its chapters print in `order`, every line kept."""
    lines, raw = _yaml_text(root)
    chapters = raw.get("chapters") or []
    names = [str(c.get("name")) for c in chapters]
    if sorted(order) != sorted(names):
        raise Problem("The chapters changed since this page loaded. Reload the page and try again.",
                      HTTPStatus.CONFLICT)
    blocks = _chapter_blocks(lines)
    if len(blocks) != len(names):
        raise config.ConfigError("the chapters list is not one `- name:` block per chapter")
    moved = [names.index(name) for name in order]
    out = lines[:blocks[0][0]]
    for slot, k in enumerate(moved):
        if slot:
            out += lines[blocks[slot - 1][2]:blocks[slot][0]]
        out += lines[blocks[k][0]:blocks[k][2]]
    out += lines[blocks[-1][2]:]
    _write_checked(root, out, {**raw, "chapters": [chapters[k] for k in moved]})


def _flow(slug: str) -> str:
    """A slug as an item of a YAML flow list: bare when YAML reads it back as itself."""
    return slug if re.fullmatch(r"[\w.-]+", slug) and yaml.safe_load(slug) == slug else json.dumps(slug)


def pin_entries(root: config.BookRoot, chapter: str, order: list[str]) -> None:
    """Rewrite the chapter's `pinned:` so its entries print in `order`. Unpinned
    entries follow alphabetically, so the list is the shortest one that gives
    the order: entries added later still slot in by name."""
    k = next(k for k in range(len(order) + 1) if order[k:] == sorted(order[k:]))
    pinned = order[:k]
    lines, raw = _yaml_text(root)
    chapters = raw.get("chapters") or []
    index = next(i for i, c in enumerate(chapters) if str(c.get("name")) == chapter)
    if not pinned and not chapters[index].get("pinned"):
        return  # already alphabetical, nothing pinned
    blocks = _chapter_blocks(lines)
    if len(blocks) != len(chapters):
        raise config.ConfigError("the chapters list is not one `- name:` block per chapter")
    _, dash, stop = blocks[index]
    col = len(re.match(r"\s*-\s*", lines[dash]).group())  # where the chapter's keys start
    value = "pinned: [" + ", ".join(_flow(s) for s in pinned) + "]"
    at = next((j for j in range(dash, stop) if lines[j][col:].startswith("pinned:")
               and (j == dash or not lines[j][:col].strip())), None)
    if at is None:
        lines[stop:stop] = [" " * col + value + "\n"]
    else:
        rest = lines[at][col + len("pinned:"):]
        drop = []
        if rest.lstrip().startswith("["):  # flow list, perhaps over several lines
            close = next(j for j in range(at, stop) if "]" in lines[j][col if j == at else 0:])
            end = lines[close].index("]", col if close == at else 0) + 1
            tail = lines[close][end:]
            lines[close] = lines[close][:end] + "\n"  # its comment, if any, moves up with the tail
            drop = list(range(at + 1, close + 1))
        else:  # a block list below the key
            tail = (" " + rest[rest.index("#"):]) if "#" in rest else "\n"
            for j in range(at + 1, stop):
                line = lines[j]
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if _indent(line) > col or (_indent(line) == col and line.lstrip().startswith("- ")):
                    drop.append(j)
                else:
                    break
        lines[at] = lines[at][:col] + value + tail
        for j in reversed(drop):  # the old items go; a comment on one stays, on its own line
            note = lines[j].find(" #")
            if note >= 0:
                lines[j] = " " * _indent(lines[j]) + lines[j][note + 1:]
            else:
                del lines[j]
    expected = copy.deepcopy(raw)
    expected["chapters"][index]["pinned"] = pinned
    _write_checked(root, lines, expected)


# -- the book as the studio shows it ------------------------------------------

def chapter_entries(root: config.BookRoot, chapter: config.Chapter) -> list[Path]:
    """The chapter's entry folders in book order."""
    from . import render

    folder = root.book / chapter.base / chapter.name
    if chapter.generated or not folder.is_dir():
        return []
    return [p for p in render.ordered_slugdirs(folder, list(chapter.pinned))
            if (p / chapter.entry_filename).exists()]


def _title(md: Path) -> str:
    return next((line[2:].strip() for line in md.read_text(encoding="utf-8").splitlines()
                 if line.startswith("# ")), md.parent.name.replace("-", " ").capitalize())


def _work(root_path: str, job: str, events) -> None:
    """One job, in a fresh process (see the module docstring). Sends ("step",
    name) as the press sequence advances, then ("done", result) or ("error", message)."""
    root = config.BookRoot(Path(root_path))
    config.activate(root)
    try:
        config.load(root)  # a book.yaml mistake in words, not load_or_exit's bare exit code
        if job == "build":
            from . import render

            render.main(print_mode=False)
            result = {}
        elif job == "report":
            from . import audit

            findings, entries = audit.collect(root)
            audit.write_report(root, findings, entries)
            per_entry: dict[str, dict[str, int]] = {}
            for f in findings:
                if f.entry:
                    counts = per_entry.setdefault(f.entry, dict.fromkeys(audit.SEVERITIES, 0))
                    counts[f.severity] += 1
            result = {"counts": {s: sum(f.severity == s for f in findings) for s in audit.SEVERITIES},
                      "by_check": audit.by_check(findings), "entries": per_entry, "checked": len(entries)}
        else:
            try:
                result = {"failing": press.run(root, lambda name: events.put(("step", name)))}
            except press.LintErrors as exc:
                shown = "; ".join(exc.errors[:3]) + ("; …" if len(exc.errors) > 3 else "")
                events.put(("error", f"The book has {len(exc.errors)} problem(s) to fix before it "
                                     f"prints: {shown}. Check the book on the Report tab to see them all."))
                return
        events.put(("done", result))
    except config.ConfigError as exc:
        events.put(("error", f"book.yaml has a mistake: {exc}"))
    except SystemExit as exc:
        events.put(("error", exc.code if isinstance(exc.code, str) else STOPPED))
    except Exception as exc:
        traceback.print_exc()
        events.put(("error", f"{STOPPED} ({type(exc).__name__}: {exc})"))


class Studio:
    """The book root, the jobs running on it, and the last book report."""

    def __init__(self, root: config.BookRoot) -> None:
        self.root = root
        self.review = review.Book(root)
        self.jobs: dict[str, dict] = {}
        self.report: dict | None = None  # the last report job's result
        self.lock = threading.Lock()      # the jobs
        self.writing = threading.Lock()   # book.yaml and extras/ edits

    # jobs

    def start(self, job: str) -> dict:
        label = JOBS[job]
        with self.lock:
            busy = next((j for j in self.jobs.values() if j["running"]), None)
            if busy:
                raise Problem(f"Wait: {busy['label'].lower()} is still running.", HTTPStatus.CONFLICT)
            state = self.jobs[job] = {"job": job, "label": label, "running": True, "step": "",
                                      "started": time.time(), "finished": None, "ok": None,
                                      "message": "", "result": None}
        threading.Thread(target=self._run, args=(job, state), daemon=True).start()
        return dict(state)

    def _run(self, job: str, state: dict) -> None:
        ctx = multiprocessing.get_context("spawn")
        events = ctx.Queue()
        proc = ctx.Process(target=_work, args=(str(self.root.path), job, events), daemon=True)
        proc.start()
        while True:
            try:
                kind, value = events.get(timeout=1)
            except queue.Empty:
                if proc.is_alive():
                    continue
                try:
                    kind, value = events.get(timeout=1)  # sent just before it exited
                except queue.Empty:
                    kind, value = "error", STOPPED
            if kind != "step":
                break
            with self.lock:
                state["step"] = value
        proc.join()
        with self.lock:
            if kind == "done" and job == "report":
                self.report = value
            state.update(running=False, finished=time.time(), ok=kind == "done",
                         result=value if kind == "done" else None, message=value if kind == "error" else "")

    def job_states(self) -> dict:
        with self.lock:
            return {name: dict(state) for name, state in self.jobs.items()}

    # the book

    def outline(self) -> dict:
        cfg = config.load(self.root)
        reviewed = {q["entry"]: q for q in self.review.queue(everything=True)}
        found = self.report["entries"] if self.report else None
        chapters = []
        for c in cfg.chapters:
            entries = []
            for folder in chapter_entries(self.root, c):
                key = folder.relative_to(self.root.book).as_posix()
                state = reviewed.get(key, {})
                entries.append({"key": key, "slug": folder.name, "title": _title(folder / c.entry_filename),
                                "approved": state.get("approved"), "original": state.get("original"),
                                "findings": found.get(key) if found else None})
            page = self.root.book / "sections" / c.name
            chapters.append({"name": c.name, "label": c.label, "kind": c.kind, "entries": entries,
                             "page": f"sections/{c.name}" if not c.generated and page.is_dir() else None})
        draft = self.root.draft / "cookbook-draft.html"
        return {"title": cfg.title, "chapters": chapters, "reported": found is not None,
                "draft": draft.stat().st_mtime if draft.exists() else None}

    def reorder(self, order: list[str]) -> dict:
        with self.writing:
            reorder_chapters(self.root, [str(n) for n in order])
        return self.outline()

    def pin(self, chapter: str, order: list[str]) -> dict:
        cfg = config.load(self.root)
        if chapter not in cfg.by_name:
            raise KeyError(chapter)
        slugs = [p.name for p in chapter_entries(self.root, cfg.by_name[chapter])]
        order = [str(s) for s in order]
        if sorted(order) != sorted(slugs):
            raise Problem("The entries changed since this page loaded. Reload the page and try again.",
                          HTTPStatus.CONFLICT)
        with self.writing:
            pin_entries(self.root, chapter, order)
        return self.outline()

    # keepsakes

    def keepsake_folders(self) -> dict[str, Path]:
        """Every folder a keepsake can print with, by key: each entry, and each
        chapter's own page (its divider, or a page like the dedication)."""
        folders = {}
        for c in config.load(self.root).chapters:
            page = self.root.book / "sections" / c.name
            if not c.generated and page.is_dir():
                folders[f"sections/{c.name}"] = page
            for folder in chapter_entries(self.root, c):
                folders[folder.relative_to(self.root.book).as_posix()] = folder
        return folders

    def extras(self, key: str) -> dict:
        from . import render

        folder = self.keepsake_folders()[key]
        base = folder / render.EXTRAS_DIR
        listed = render.extras_listing(folder)
        names = {name for name, _ in listed}
        return {
            "entry": key,
            "listed": [{"file": name, "caption": caption, "missing": not (base / name).is_file(),
                        "url": f"/book/{quote(key)}/{render.EXTRAS_DIR}/{quote(name)}"} for name, caption in listed],
            "unlisted": sorted(p.name for p in base.iterdir() if p.is_file() and p.name not in names
                               and p.suffix.lower() in render.EXTRA_SUFFIXES) if base.is_dir() else [],
        }

    def add_extra(self, key: str, filename: str, caption: str, data: bytes) -> dict:
        """Save the picture into the entry's extras/ and list it, captioned, last in extras.md."""
        from . import render

        folder = self.keepsake_folders()[key]
        caption = " ".join(caption.split())
        if not caption:
            raise Problem("Write a caption: who or what is in the picture, and roughly when.")
        if "[" in caption or "]" in caption:
            raise Problem("A caption cannot contain square brackets.")
        suffix = next((s for magic, s in PICTURE_TYPES.items() if data.startswith(magic)), None)
        if suffix is None:
            raise Problem("Only JPG and PNG pictures can print. Save it as a JPG (most phones can share "
                          "a photo as JPG) and add it again.")
        stem = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "keepsake"
        base = folder / render.EXTRAS_DIR
        with self.writing:
            base.mkdir(exist_ok=True)
            name, n = f"{stem}{suffix}", 1
            while (base / name).exists():
                n += 1
                name = f"{stem}-{n}{suffix}"
            (base / name).write_bytes(data)
            listing = base / render.EXTRAS_LIST
            text = listing.read_text(encoding="utf-8") if listing.exists() else "# Extras\n\n"
            listing.write_text(text + ("" if text.endswith("\n") else "\n") + f"![{caption}]({name})\n",
                               encoding="utf-8")
        return self.extras(key)

    def remove_extra(self, key: str, name: str) -> dict:
        """Delete the picture and its line in extras.md. An extras.md left listing
        nothing goes too (lint calls it an error), unless it holds the family's notes."""
        from . import render

        folder = self.keepsake_folders()[key]
        if name not in {n for n, _ in render.extras_listing(folder)}:
            raise KeyError(name)
        base = folder / render.EXTRAS_DIR
        listing = base / render.EXTRAS_LIST
        with self.writing:
            kept = [line for line in listing.read_text(encoding="utf-8").splitlines(keepends=True)
                    if not ((m := render.EXTRA_LINE.match(line)) and m.group("file").strip() == name)]
            notes = [line for line in kept if line.strip() and not line.startswith("# ")]
            if notes:
                listing.write_text("".join(kept), encoding="utf-8")
            else:
                listing.unlink()
            picture = (base / name).resolve()
            if picture.parent == base.resolve() and picture.suffix.lower() in render.EXTRA_SUFFIXES:
                picture.unlink(missing_ok=True)
            if not any(base.iterdir()):
                base.rmdir()
        return self.extras(key)

    # proof

    def proof_state(self) -> dict:
        """The press PDFs as built: each one's size, and the interior's page count
        (from poppler's pdfinfo, when it is installed). None before the first press."""
        interior, cover = self.root.draft / "cookbook-interior-press.pdf", self.root.draft / "cookbook-cover.pdf"
        if not (interior.is_file() and cover.is_file()):
            return {"files": None}
        pages = None
        if shutil.which("pdfinfo"):
            out = subprocess.run(["pdfinfo", str(interior)], capture_output=True, text=True).stdout
            pages = next((int(line.split(":")[1]) for line in out.splitlines() if line.startswith("Pages:")), None)
        return {"files": {"pages": pages, "interior_bytes": interior.stat().st_size,
                          "cover_bytes": cover.stat().st_size}}


class Handler(review.Handler):
    """review.py's handler, which serves its editor at /review and its own
    /api/queue, /api/entry, /api/save, /api/approve, and /file/ routes, plus the studio."""
    studio: Studio

    def _answer(self, work) -> None:
        try:
            self._json(work())
        except Problem as exc:
            self._json({"error": str(exc)}, exc.status)
        except config.ConfigError as exc:
            self._json({"error": f"book.yaml was not changed: {exc}."}, HTTPStatus.BAD_REQUEST)
        except (KeyError, IndexError, FileNotFoundError):
            self._json({"error": "That is not part of this book. Reload the page."}, HTTPStatus.NOT_FOUND)
        except (Exception, SystemExit) as exc:
            traceback.print_exc()
            self._json({"error": f"Something went wrong ({type(exc).__name__}: {exc}). "
                                 "The terminal running cookbook studio has the details."},
                       HTTPStatus.INTERNAL_SERVER_ERROR)

    def _file(self, base: Path, rel: str, kinds: set[str]) -> None:
        """A file under `base`, of one of `kinds`; nothing outside it, whatever the path says."""
        path = (base / unquote(rel)).resolve()
        if not path.is_relative_to(base.resolve()) or path.suffix.lower() not in kinds or not path.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", kind + ("; charset=utf-8" if kind == "text/html" else ""))
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        studio = self.studio
        if url.path == "/":
            page = PAGE.replace("__PRINTING_URL__", press.PRINTING_URL)
            self._send(HTTPStatus.OK, page.encode(), "text/html; charset=utf-8")
        elif url.path == "/review":
            self._send(HTTPStatus.OK, review.PAGE.encode(), "text/html; charset=utf-8")
        elif url.path.startswith("/draft/"):
            self._file(studio.root.draft, url.path[len("/draft/"):], DRAFT_TYPES)
        elif url.path.startswith("/book/"):  # the draft's ../book/ pictures
            self._file(studio.root.book, url.path[len("/book/"):], review.IMAGE_TYPES)
        elif url.path == "/api/book":
            self._answer(studio.outline)
        elif url.path == "/api/jobs":
            self._answer(studio.job_states)
        elif url.path == "/api/extras":
            self._answer(lambda: studio.extras(query["entry"][0]))
        elif url.path == "/api/proof":
            self._answer(studio.proof_state)
        else:
            super().do_GET()

    def do_POST(self) -> None:
        url = urlparse(self.path)
        studio = self.studio
        routes = {
            "/api/chapters": lambda body: studio.reorder(body["order"]),
            "/api/entries": lambda body: studio.pin(body["chapter"], body["order"]),
            "/api/extras/remove": lambda body: studio.remove_extra(body["entry"], body["file"]),
        }
        if url.path.startswith("/api/jobs/"):
            self._answer(lambda: studio.start(url.path[len("/api/jobs/"):]))
        elif url.path == "/api/extras":
            self._answer(self._upload)
        elif url.path in routes:
            self._answer(lambda: routes[url.path](self._body()))
        else:
            super().do_POST()

    def _upload(self) -> dict:
        """POST /api/extras?entry=&caption=&name= with the picture's bytes as the body."""
        query = parse_qs(urlparse(self.path).query)
        size = int(self.headers.get("Content-Length", 0))
        if size > MAX_UPLOAD:
            self.close_connection = True  # the body stays unread
            raise Problem("That picture is over 25 MB. Save it as a smaller JPG and add it again.",
                          HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        key = query["entry"][0]
        self.studio.keepsake_folders()[key]  # an unknown entry is refused before the upload is read
        return self.studio.add_extra(key, query.get("name", [""])[0], query.get("caption", [""])[0],
                                     self.rfile.read(size))


def serve(root: config.BookRoot, port: int) -> ThreadingHTTPServer:
    handler = type("StudioHandler", (Handler,), {"book": review.Book(root), "everything": True,
                                                 "studio": Studio(root)})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main(root: config.BookRoot, *, port: int = 8770, open_browser: bool = True) -> int:
    try:
        server = serve(root, port)
    except OSError as exc:
        print(f"error: cannot use port {port} ({exc.strerror}): is the studio already open? "
              f"Or pass --port {port + 1}", file=sys.stderr)
        return 2
    url = f"http://127.0.0.1:{port}/"
    print(f"Studio for {root.path.name} at {url} — Ctrl+C to stop.", flush=True)
    server.RequestHandlerClass.studio.start("report")  # the recipe list shows the report's findings from the start
    if open_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cookbook studio</title>
<style>
  :root {
    --paper: #faf7f2; --ink: #2a2622; --muted: #6b635b; --rule: #e2dbd1; --field: #cfc6ba;
    --accent: #8a5a2b; --ok: #2f6b3f;
    --error: #a3271f; --error-bg: #fbe9e7;
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); background: var(--paper);
  }
  * { box-sizing: border-box; }
  body { margin: 0; }
  [hidden] { display: none !important; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .skip { position: absolute; left: -999px; top: .5rem; background: #fff; padding: .4rem .7rem; z-index: 10; }
  .skip:focus { left: 1rem; }
  header.top { position: sticky; top: 0; z-index: 5; background: var(--paper); border-bottom: 1px solid var(--rule);
               padding: .75rem 1.25rem 0; }
  .brand { display: flex; flex-wrap: wrap; align-items: baseline; gap: .15rem 1rem; }
  .brand h1 { font-size: 1.15rem; margin: 0; }
  .brand small { color: var(--muted); font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; }
  #busy { margin: 0; color: var(--muted); font-size: .9rem; min-height: 1.35em; }
  #busy.ok { color: var(--ok); } #busy.bad { color: var(--error); }
  [role="tablist"] { display: flex; flex-wrap: wrap; gap: .15rem; margin-top: .4rem; }
  [role="tab"] { font: inherit; background: none; border: 0; border-bottom: 3px solid transparent; color: var(--muted);
                 padding: .45rem .7rem; cursor: pointer; border-radius: 6px 6px 0 0; }
  [role="tab"]:hover { background: #efe8de; color: var(--ink); }
  [role="tab"][aria-selected="true"] { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
  [role="tab"]:focus-visible { outline-offset: -2px; }
  main { padding: 1rem 1.25rem 3rem; }
  [role="tabpanel"] { max-width: 62rem; }
  [role="tabpanel"].wide { max-width: none; }
  [role="tabpanel"]:focus-visible { outline-offset: 4px; }
  h2 { font-size: 1.05rem; margin: 1.25rem 0 .5rem; }
  .lead { color: var(--muted); margin: 0 0 1rem; max-width: 46rem; }
  .hint { color: var(--muted); font-size: .85rem; margin: .25rem 0 0; }
  .bar { display: flex; flex-wrap: wrap; gap: .6rem 1rem; align-items: center; margin: 0 0 .75rem; }
  .bar label { display: inline; margin: 0; }
  .bar select { width: auto; }
  button { font: inherit; padding: .5rem 1rem; border-radius: 6px; border: 1px solid var(--accent); background: #fff;
           color: var(--accent); cursor: pointer; }
  button.primary { background: var(--accent); color: #fff; }
  button.small { padding: .2rem .6rem; font-size: .85rem; }
  button.danger { border-color: var(--error); color: var(--error); }
  button:hover:not(:disabled) { box-shadow: 0 1px 3px rgba(0,0,0,.15); }
  button:disabled { opacity: .45; cursor: default; }
  a { color: var(--accent); }
  .status { color: var(--muted); font-size: .9rem; margin: 0 0 .75rem; min-height: 1.35em; }
  .status.ok { color: var(--ok); } .status.bad { color: var(--error); }
  label { display: block; font-weight: 600; font-size: .9rem; margin-bottom: .2rem; }
  input[type="text"], select {
    font: inherit; width: 100%; max-width: 30rem; padding: .45rem .55rem; color: var(--ink); background: #fff;
    border: 1px solid var(--field); border-radius: 6px; }
  input[type="file"] { font: inherit; max-width: 100%; }
  [aria-invalid="true"] { border-color: var(--error) !important; }
  .field { margin: 0 0 .9rem; }
  .card { background: #fff; border: 1px solid var(--rule); border-radius: 8px; padding: .25rem 1rem 1rem; margin: 1rem 0; }
  .card > .hint { margin-bottom: .75rem; }
  .badge { display: inline-block; padding: .35rem .65rem; border-radius: 6px; font-size: .9rem; margin: 0 0 .75rem; }
  .badge.bad { background: var(--error-bg); color: var(--error); }
  .frame { display: block; width: 100%; height: calc(100vh - 12.5rem); min-height: 24rem; background: #d9d4cc;
           border: 1px solid var(--rule); border-radius: 6px; }
  /* Recipes */
  .group { list-style: none; margin: 0 0 1rem; padding: 0; display: grid; gap: .3rem; }
  .entry { display: flex; flex-wrap: wrap; gap: .1rem 1rem; width: 100%; text-align: left; color: var(--ink);
           border-color: var(--rule); }
  .entry .meta { margin-left: auto; color: var(--muted); font-size: .85rem; }
  .entry .meta.flagged { color: var(--error); }
  /* Chapters */
  .chapters { list-style: none; margin: 0; padding: 0; display: grid; gap: .45rem; }
  .chapters > li { background: #fff; border: 1px solid var(--rule); border-radius: 8px; padding: .45rem .75rem; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem .5rem; }
  .row .name { flex: 1 1 12rem; min-width: 0; }
  .kind { color: var(--muted); font-size: .8rem; margin-left: .5rem; }
  .entries { list-style: none; margin: .5rem 0 .25rem; padding: 0 0 0 .75rem; border-left: 2px solid var(--rule);
             display: grid; gap: .3rem; }
  /* Keepsakes */
  .keepsakes { list-style: none; margin: 0; padding: 0; display: grid; gap: .75rem;
               grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr)); }
  .keepsakes li { background: #fff; border: 1px solid var(--rule); border-radius: 8px; padding: .6rem; }
  .keepsakes figure { margin: 0; }
  .keepsakes img { display: block; width: 100%; height: 11rem; object-fit: contain; background: #f1ede7; border-radius: 4px; }
  figcaption { font-style: italic; font-size: .9rem; margin: .4rem 0; }
  @media (max-width: 700px) {
    header.top { padding: .6rem .75rem 0; }
    main { padding: .75rem .75rem 3rem; }
    [role="tab"] { padding: .4rem .5rem; }
    .row .name { flex-basis: 100%; }
    .frame { height: calc(100vh - 16rem); }
  }
</style>
</head>
<body>
<a class="skip" href="#main">Skip to the open tab</a>
<header class="top">
  <div class="brand"><h1 id="title">Cookbook studio</h1><small>Cookbook studio</small></div>
  <p id="busy" role="status" aria-live="polite"></p>
  <div role="tablist" aria-label="Studio">
    <button role="tab" type="button" id="tab-book" aria-controls="book" aria-selected="true">Book</button>
    <button role="tab" type="button" id="tab-recipes" aria-controls="recipes" aria-selected="false" tabindex="-1">Recipes</button>
    <button role="tab" type="button" id="tab-chapters" aria-controls="chapters" aria-selected="false" tabindex="-1">Chapters</button>
    <button role="tab" type="button" id="tab-keepsakes" aria-controls="keepsakes" aria-selected="false" tabindex="-1">Photos &amp; keepsakes</button>
    <button role="tab" type="button" id="tab-report" aria-controls="report" aria-selected="false" tabindex="-1">Report</button>
    <button role="tab" type="button" id="tab-proof" aria-controls="proof" aria-selected="false" tabindex="-1">Proof</button>
  </div>
</header>
<main id="main">

<section role="tabpanel" id="book" aria-labelledby="tab-book" tabindex="0" class="wide">
  <div class="bar">
    <button type="button" class="primary job" data-job="build">Rebuild the book</button>
    <label for="zoom">Size</label>
    <select id="zoom"><option value="fit">Fit the width</option><option value="1">Actual size</option></select>
    <a href="/draft/cookbook-draft.html" target="_blank" rel="noopener">Open in a new tab</a>
  </div>
  <p class="status" id="status-build"></p>
  <p class="lead" id="no-draft" hidden>There is no draft yet. Press Rebuild the book to make one.</p>
  <iframe class="frame" id="draft" title="The book as facing pages"></iframe>
</section>

<section role="tabpanel" id="recipes" aria-labelledby="tab-recipes" tabindex="0" class="wide" hidden>
  <div id="recipe-list">
    <p class="lead">Select a recipe to check it against its original card or page, correct it, and approve it.
      What the book check found in each comes from the Report tab.</p>
    <div id="recipe-groups"></div>
  </div>
  <div id="recipe-editor" hidden>
    <div class="bar"><button type="button" id="recipe-back">Back to all recipes</button></div>
    <iframe class="frame" id="editor" title="Recipe editor"></iframe>
  </div>
</section>

<section role="tabpanel" id="chapters" aria-labelledby="tab-chapters" tabindex="0" hidden>
  <p class="lead">The book prints in this order. Move a chapter with Move up and Move down, or open a chapter to
    change the order of its recipes or pages. Each change is saved to book/book.yaml at once; rebuild the book to see it.</p>
  <div class="bar"><button type="button" class="job" data-job="build" data-then="book">Rebuild the book and show it</button></div>
  <p class="status" id="status-chapters" role="status" aria-live="polite"></p>
  <ol class="chapters" id="chapter-list"></ol>
</section>

<section role="tabpanel" id="keepsakes" aria-labelledby="tab-keepsakes" tabindex="0" hidden>
  <p class="lead">Card scans, family photos, and letters print with the recipe or page they belong to, captioned,
    at the foot of its page or on a keepsake page right after it.</p>
  <div class="field"><label for="ks-entry">Recipe or page</label><select id="ks-entry"></select></div>
  <h2>Printed with it</h2>
  <ul class="keepsakes" id="ks-list"></ul>
  <p class="hint" id="ks-empty">Nothing yet.</p>
  <p class="hint" id="ks-unlisted"></p>
  <form id="ks-form" class="card" novalidate>
    <h2>Add a keepsake</h2>
    <div class="field">
      <label for="ks-file">Picture</label>
      <input type="file" id="ks-file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" aria-describedby="ks-file-hint">
      <p class="hint" id="ks-file-hint">A JPG or PNG, up to 25 MB. Scan cards flat, in good light, at 300 to 600 dpi.</p>
    </div>
    <div class="field">
      <label for="ks-caption">Caption</label>
      <input type="text" id="ks-caption" aria-describedby="ks-caption-hint">
      <p class="hint" id="ks-caption-hint">Who or what, and roughly when, as the family knows it: "Grandma's card, in her
        own hand, about 1980". Never guess a name or a year; ask.</p>
    </div>
    <button type="submit" class="primary" id="ks-add">Add to the book</button>
    <p class="status" id="status-ks" role="status" aria-live="polite"></p>
  </form>
</section>

<section role="tabpanel" id="report" aria-labelledby="tab-report" tabindex="0" class="wide" hidden>
  <p class="lead">The book check reads every recipe for what a careful reader would catch: a cook time the directions
    do not support, an ingredient missing from the list, a line of the original left out. It adds the layout and
    photo checks too.</p>
  <div class="bar">
    <button type="button" class="primary job" data-job="report">Check the book</button>
    <a href="/draft/book-report.html" target="_blank" rel="noopener">Open the report in a new tab</a>
  </div>
  <p class="status" id="status-report"></p>
  <p id="report-summary"></p>
  <iframe class="frame" id="report-frame" title="The book report"></iframe>
</section>

<section role="tabpanel" id="proof" aria-labelledby="tab-proof" tabindex="0" hidden>
  <p class="lead">The print files are the two PDFs the printer prints: the pages and the cover. Making them lays the
    book out at print size, checks every page, and writes both files. It takes a few minutes.</p>
  <div class="bar"><button type="button" class="primary job" data-job="proof">Make the print files</button></div>
  <p class="status" id="status-proof"></p>
  <div id="proof-failing" class="card" hidden>
    <h2>Pages to fix first</h2>
    <ul id="failing-list"></ul>
    <p>Fix each page as it says, then make the print files again.</p>
  </div>
  <p class="hint" id="proof-none" hidden>There are no print files yet.</p>
  <div id="proof-files" hidden>
    <h2>The print files</h2>
    <p id="proof-pages"></p>
    <ul>
      <li><a href="/draft/cookbook-interior-press.pdf" target="_blank" rel="noopener">The pages</a> <span class="hint" id="size-interior"></span></li>
      <li><a href="/draft/cookbook-cover.pdf" target="_blank" rel="noopener">The cover</a> <span class="hint" id="size-cover"></span></li>
    </ul>
    <p>These two files are what a printer needs. To print through Lulu yourself, follow the steps in the
      engine's <a href="__PRINTING_URL__" target="_blank" rel="noopener">printing guide</a>.</p>
  </div>
</section>
</main>
<script>
const $ = (id) => document.getElementById(id);
function el(tag, props = {}, ...kids) { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; }
function plural(n, one, many) { return `${n} ${n === 1 ? one : (many || one + "s")}`; }
function clock(t) { return new Date(t * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
function mb(bytes) { return `(${(bytes / 1048576).toFixed(1)} MB)`; }
// Writes a status line; the same words again are left alone, so a screen reader hears each change once.
function say(id, text, kind) {
  const s = $(id), cls = (id === "busy" ? "" : "status ") + (kind || "");
  if (s.textContent !== text || s.className !== cls) { s.textContent = text; s.className = cls; }
}

async function api(url, body) {
  const init = body === undefined ? {} : body instanceof Blob ? { method: "POST", body }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  let res;
  try { res = await fetch(url, init); }
  catch { throw new Error("The studio is not answering. Is cookbook studio still running in its terminal window?"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `The studio could not do that (${res.status}).`);
  return data;
}

// A long action runs once: its button stays off until the action ends.
async function once(button, work) {
  if (button.disabled) return;
  button.disabled = true;
  try { await work(); } finally { button.disabled = false; syncButtons(); }
}

// ---- tabs
const tabs = [...document.querySelectorAll('[role="tab"]')];
const loaders = { book: showDraft, recipes: loadRecipes, chapters: loadChapters, keepsakes: loadKeepsakes,
                  report: loadReport, proof: loadProof };
function select(tab, focus) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  }
  if (focus) tab.focus();
  const name = tab.getAttribute("aria-controls");
  history.replaceState(null, "", "#" + name);
  Promise.resolve(loaders[name]()).catch((err) => say("busy", err.message, "bad"));
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => select(t));
  t.addEventListener("keydown", (e) => {
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault(); select(tabs[(to + tabs.length) % tabs.length], true);
  });
});

// ---- jobs: rebuild, check, print files; one at a time, run by the studio
let jobs = {}, timer = null, shown = {};  // shown: the text each job's status last got from here
const STEPS = { "lint": "checking the book's files", "fit": "fitting the photos",
  "build --print": "laying out the pages at print size",
  "check": "checking every page, the longest step", "export interior": "writing the pages PDF",
  "cover": "laying out the cover", "export cover": "writing the cover PDF" };
function jobText(j) {
  if (j.running) {
    const names = Object.keys(STEPS), step = j.step ? `: step ${names.indexOf(j.step) + 1} of ${names.length}, ${STEPS[j.step]}` : "";
    return [`${j.label}${step}. Started at ${clock(j.started)}.`, ""];
  }
  if (!j.ok) return [`${j.label} stopped. ${j.message}`, "bad"];
  if (j.job === "build") return [`The book was rebuilt at ${clock(j.finished)}.`, "ok"];
  if (j.job === "report") return [`The book was checked at ${clock(j.finished)}.`, "ok"];
  const n = j.result.failing.length;
  return n ? [`The print files stopped at the page check: ${plural(n, "page")} to fix, listed on the Proof tab.`, "bad"]
           : [`The print files were made at ${clock(j.finished)}.`, "ok"];
}
function syncButtons() {
  const running = Object.values(jobs).some((j) => j.running);
  document.querySelectorAll("button.job").forEach((b) => { b.disabled = running; });
}
async function pollJobs() {
  clearTimeout(timer);
  let now;
  try { now = await api("/api/jobs"); }
  catch (err) { say("busy", err.message, "bad"); timer = setTimeout(pollJobs, 3000); return; }
  const before = jobs; jobs = now;
  for (const [name, j] of Object.entries(jobs)) {
    const [text, kind] = jobText(j);
    if (shown[name] !== text) { shown[name] = text; say("status-" + name, text, kind); }
    if (j.running || (before[name] && before[name].running)) say("busy", text, kind);
  }
  syncButtons();
  for (const [name, j] of Object.entries(jobs)) {
    if (before[name] && before[name].running && !j.running) finished(name);
  }
  if (Object.values(jobs).some((j) => j.running)) timer = setTimeout(pollJobs, 1000);
}
function finished(name) {
  const open = tabs.find((t) => t.getAttribute("aria-selected") === "true").getAttribute("aria-controls");
  if (name === "build" && open === "book") showDraft();
  if (name === "report" && (open === "report" || open === "recipes")) loaders[open]();
  if (name === "proof" && open === "proof") loadProof();
}
document.querySelectorAll("button.job").forEach((b) => b.addEventListener("click", async () => {
  if (b.disabled) return;
  b.disabled = true;
  try {
    await api("/api/jobs/" + b.dataset.job, {});
    if (b.dataset.then) select($("tab-" + b.dataset.then), true);
  } catch (err) { say("status-" + b.dataset.job, err.message, "bad"); }
  await pollJobs();
  if (b.dataset.job === "proof") loadProof();
}));

// ---- Book
let draftShown = null;
async function showDraft() {
  const book = await api("/api/book");
  $("no-draft").hidden = !!book.draft; $("draft").hidden = !book.draft;
  if (book.draft && book.draft !== draftShown) { draftShown = book.draft; $("draft").src = "/draft/cookbook-draft.html?v=" + book.draft; }
  else fitDraft();
}

// Fit one spread (two pages and the draft's padding) to the frame's width. The draft centers its
// spreads, which hides a spread's left page when the window is narrower; "safe" keeps it reachable.
function fitDraft() {
  const frame = $("draft"), doc = frame.contentDocument;
  const book = doc && doc.querySelector(".book"), page = book && book.querySelector(".page");
  if (!page || !frame.clientWidth) return;
  book.style.justifyContent = "safe center";
  doc.documentElement.style.zoom = 1;
  const spread = 2 * page.offsetWidth + 2 * parseFloat(getComputedStyle(book).paddingLeft);
  if ($("zoom").value === "fit") doc.documentElement.style.zoom = Math.min(1, (frame.clientWidth - 20) / spread);
}
$("draft").addEventListener("load", fitDraft);
$("zoom").addEventListener("change", fitDraft);
window.addEventListener("resize", fitDraft);

// ---- Recipes: the list here, the editor from cookbook review
let editing = null;
function findings(e, reported) {
  const parts = [e.original === false ? "Hand-written, no original to check"
                 : e.approved ? "Approved" : "Not approved yet"];
  const f = e.findings;
  if (!reported) parts.push("not checked yet");
  else if (!f) parts.push("nothing flagged");
  else parts.push([f.error && plural(f.error, "error"), f.warning && plural(f.warning, "warning"),
                   f.note && plural(f.note, "note")].filter(Boolean).join(", ") || "nothing flagged");
  return parts.join(" · ");
}
async function loadRecipes() {
  if (!$("recipe-editor").hidden) return;
  const book = await api("/api/book");
  const box = $("recipe-groups"); box.replaceChildren();
  for (const c of book.chapters.filter((c) => c.kind === "recipes")) {
    const ul = el("ul", { className: "group" });
    for (const e of c.entries) {
      const meta = el("span", { className: "meta" + (e.findings && e.findings.error ? " flagged" : ""), textContent: findings(e, book.reported) });
      const b = el("button", { type: "button", className: "entry" }, el("span", { textContent: e.title }), meta);
      b.dataset.key = e.key;
      b.addEventListener("click", () => openEditor(e.key));
      ul.append(el("li", {}, b));
    }
    if (!c.entries.length) ul.append(el("li", { className: "hint", textContent: "No recipes in this chapter yet." }));
    box.append(el("h2", { textContent: c.label }), ul);
  }
}
function openEditor(key) {
  editing = key;
  $("recipe-list").hidden = true; $("recipe-editor").hidden = false;
  $("editor").src = "/review?e=" + encodeURIComponent(key);
  $("recipe-back").focus();
}
$("recipe-back").addEventListener("click", async () => {
  $("recipe-editor").hidden = true; $("recipe-list").hidden = false; $("editor").src = "about:blank";
  await loadRecipes();
  const b = document.querySelector(`#recipe-groups [data-key="${CSS.escape(editing)}"]`);
  if (b) b.focus();
});

// ---- Chapters
let outline = null, openChapter = null, moving = false;
const KINDS = { recipes: "Recipes", prose: "Pages", generated: "Made by the book" };
function mover(id, text, label, disabled, action) {
  const b = el("button", { type: "button", className: "small", id, textContent: text, disabled });
  b.setAttribute("aria-label", `${text}: ${label}`);
  b.addEventListener("click", action);
  return b;
}
function renderChapters(focusId) {
  const list = $("chapter-list"); list.replaceChildren();
  const all = outline.chapters;
  all.forEach((c, i) => {
    const row = el("div", { className: "row" },
      el("span", { className: "name" }, el("strong", { textContent: c.label }), el("span", { className: "kind", textContent: KINDS[c.kind] || c.kind })),
      mover(`up-${c.name}`, "Move up", c.label, i === 0, () => moveChapter(i, -1)),
      mover(`down-${c.name}`, "Move down", c.label, i === all.length - 1, () => moveChapter(i, 1)));
    const li = el("li", {}, row);
    if (c.entries.length > 1) {
      const what = c.kind === "recipes" ? "recipes" : "pages";
      const toggle = el("button", { type: "button", className: "small", id: `open-${c.name}`, textContent: `Order of ${what} (${c.entries.length})` });
      toggle.setAttribute("aria-expanded", String(openChapter === c.name));
      toggle.setAttribute("aria-controls", `entries-${c.name}`);
      toggle.addEventListener("click", () => { openChapter = openChapter === c.name ? null : c.name; renderChapters(toggle.id); });
      row.append(toggle);
      if (openChapter === c.name) {
        const ol = el("ol", { className: "entries", id: `entries-${c.name}` });
        ol.setAttribute("aria-label", `Order of ${what} in ${c.label}`);
        c.entries.forEach((e, j) => ol.append(el("li", { className: "row" }, el("span", { className: "name", textContent: e.title }),
          mover(`up-${c.name}--${e.slug}`, "Move up", e.title, j === 0, () => moveEntry(c, j, -1)),
          mover(`down-${c.name}--${e.slug}`, "Move down", e.title, j === c.entries.length - 1, () => moveEntry(c, j, 1)))));
        li.append(ol);
      }
    }
    list.append(li);
  });
  if (!focusId) return;
  // Keep the keyboard where it was: on the same button, or its partner once the item reaches an end.
  const target = $(focusId), partner = $(focusId.replace(/^(up|down)-/, (m, d) => (d === "up" ? "down-" : "up-")));
  (target && !target.disabled ? target : partner || target).focus();
}
async function loadChapters() { outline = await api("/api/book"); renderChapters(); }
async function saveOrder(url, body, focusId, done) {
  if (moving) return;
  moving = true;
  try { outline = await api(url, body); renderChapters(focusId); say("status-chapters", done + " Saved to book.yaml; rebuild the book to see it.", "ok"); }
  catch (err) { say("status-chapters", err.message, "bad"); }
  finally { moving = false; }
}
function moveChapter(i, delta) {
  const names = outline.chapters.map((c) => c.name), [name] = names.splice(i, 1);
  names.splice(i + delta, 0, name);
  const label = outline.chapters[i].label, dir = delta < 0 ? "up" : "down";
  saveOrder("/api/chapters", { order: names }, `${dir}-${name}`, `Moved ${label} ${dir}.`);
}
function moveEntry(c, j, delta) {
  const slugs = c.entries.map((e) => e.slug), [slug] = slugs.splice(j, 1);
  slugs.splice(j + delta, 0, slug);
  const dir = delta < 0 ? "up" : "down";
  saveOrder("/api/entries", { chapter: c.name, order: slugs }, `${dir}-${c.name}--${slug}`, `Moved ${c.entries[j].title} ${dir}.`);
}

// ---- Photos & keepsakes
async function loadKeepsakes() {
  const book = await api("/api/book"), select = $("ks-entry"), kept = select.value;
  select.replaceChildren();
  for (const c of book.chapters.filter((c) => c.kind !== "generated")) {
    const group = el("optgroup", { label: c.label });
    if (c.page) group.append(el("option", { value: c.page, textContent: `${c.label}: the chapter's own page` }));
    for (const e of c.entries) group.append(el("option", { value: e.key, textContent: e.title }));
    if (group.children.length) select.append(group);
  }
  if ([...select.options].some((o) => o.value === kept)) select.value = kept;
  await showKeepsakes();
}
async function showKeepsakes() {
  const key = $("ks-entry").value;
  if (!key) return;
  const data = await api("/api/extras?entry=" + encodeURIComponent(key));
  const list = $("ks-list"); list.replaceChildren();
  for (const k of data.listed) {
    const figure = el("figure", {}, k.missing ? el("p", { className: "badge bad", textContent: `${k.file} is listed but not in the folder.` })
                                              : el("img", { src: k.url, alt: "" }),
                      el("figcaption", { textContent: k.caption || "No caption" }));
    const remove = el("button", { type: "button", className: "small danger", textContent: "Remove" });
    remove.setAttribute("aria-label", `Remove: ${k.caption || k.file}`);
    remove.addEventListener("click", () => once(remove, async () => {
      if (!confirm(`Remove "${k.caption || k.file}" from the book? Its picture file is deleted from the extras folder.`)) return;
      try { await api("/api/extras/remove", { entry: key, file: k.file }); say("status-ks", "Removed. Rebuild the book to see the change.", "ok"); await showKeepsakes(); $("ks-entry").focus(); }
      catch (err) { say("status-ks", err.message, "bad"); }
    }));
    list.append(el("li", {}, figure, remove));
  }
  $("ks-empty").hidden = data.listed.length > 0;
  $("ks-unlisted").textContent = data.unlisted.length ? `Also in its extras folder, not printed: ${data.unlisted.join(", ")}.` : "";
}
$("ks-entry").addEventListener("change", () => showKeepsakes().catch((err) => say("status-ks", err.message, "bad")));
for (const id of ["ks-file", "ks-caption"]) $(id).addEventListener("input", () => $(id).removeAttribute("aria-invalid"));
function invalid(status, field, message) { say(status, message, "bad"); $(field).setAttribute("aria-invalid", "true"); $(field).focus(); }
$("ks-form").addEventListener("submit", (e) => { e.preventDefault(); once($("ks-add"), async () => {
  const file = $("ks-file").files[0], caption = $("ks-caption").value.trim();
  if (!file) return invalid("status-ks", "ks-file", "Choose a picture first.");
  if (!/[.](jpe?g|png)$/i.test(file.name)) return invalid("status-ks", "ks-file", "Only JPG and PNG pictures can print. Save it as a JPG (most phones can share a photo as JPG) and add it again.");
  if (file.size > 25 * 1048576) return invalid("status-ks", "ks-file", "That picture is over 25 MB. Save it as a smaller JPG and add it again.");
  if (!caption) return invalid("status-ks", "ks-caption", "Write a caption: who or what is in the picture, and roughly when.");
  say("status-ks", "Adding the picture…");
  const query = new URLSearchParams({ entry: $("ks-entry").value, caption, name: file.name });
  try {
    await api("/api/extras?" + query, file);
    $("ks-file").value = ""; $("ks-caption").value = "";
    say("status-ks", "Added. Rebuild the book to see it on the page.", "ok");
    await showKeepsakes();
  } catch (err) { say("status-ks", err.message, "bad"); }
}); });

// ---- Report
async function loadReport() {
  const j = jobs.report, r = j && j.ok && j.result;
  if (!r) { $("report-summary").textContent = j && j.running ? "" : "Press Check the book to see what it finds."; return; }
  const c = r.counts;
  $("report-summary").textContent = `${plural(c.error, "error")}, ${plural(c.warning, "warning")}, ${plural(c.note, "note")} across ${plural(r.checked, "entry", "entries")}.` + (r.by_check ? ` By check: ${r.by_check}.` : "");
  const src = "/draft/book-report.html?v=" + j.finished;
  if ($("report-frame").getAttribute("src") !== src) $("report-frame").src = src;
}

// ---- Proof
async function loadProof() {
  const j = jobs.proof, failing = j && j.ok ? j.result.failing : [];
  $("proof-failing").hidden = !failing.length;
  $("failing-list").replaceChildren(...failing.map((p) => el("li", {},
    el("strong", { textContent: (p.num ? `Page ${p.num}` : `PDF page ${p.idx}`) + (p.entry ? `: ${p.entry}` : "") }),
    el("br"), `${p.problem} ${p.fix}`)));
  if (j && j.running) { $("proof-files").hidden = true; $("proof-none").hidden = true; return; }  // the old files are being replaced
  const state = await api("/api/proof");
  $("proof-none").hidden = !!state.files; $("proof-files").hidden = !state.files;
  if (!state.files) return;
  $("proof-pages").textContent = state.files.pages ? `The book has ${state.files.pages} pages.` : "";
  $("size-interior").textContent = mb(state.files.interior_bytes); $("size-cover").textContent = mb(state.files.cover_bytes);
}

// ---- start
(async () => {
  try { const book = await api("/api/book"); $("title").textContent = book.title; document.title = `${book.title} · Cookbook studio`; }
  catch (err) { say("busy", err.message, "bad"); }
  await pollJobs();
  select(tabs.find((t) => "#" + t.getAttribute("aria-controls") === location.hash) || tabs[0]);
})();
</script>
</body>
</html>
"""
