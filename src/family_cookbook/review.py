"""`cookbook review`: check each transcribed recipe against its original.

A small local web app (standard library only) shows one recipe at a time, in
three columns: the page images, the verbatim transcription, and recipe.md in an
editor. Above them: what `cookbook ingest` flagged (CHECK) and interpreted
(NOTE), and what `cookbook audit`'s content checks find in the entry now.

Saving rewrites recipe.md and runs lint's checks on the entry. Approving saves,
refuses an entry lint rejects, and appends to book/sources/review-log.jsonl the
time the recipe was on screen and whether it was edited. An approval holds for
the recipe.md it approved: edit the file afterwards, by hand or by any tool,
and the recipe is back in the queue.

`cookbook review --report` prints the same numbers without the app: the
recipes reviewed, how many needed edits, and the average time per recipe,
against a two-minute-per-recipe review target.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config, models

REVIEW_LOG = "review-log.jsonl"
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
TARGET_SECONDS = 120  # a two-minute-per-recipe review target


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verbatim(folder: Path) -> str:
    original = folder / "sources" / "recipe-original.md"
    if not original.exists():
        return ""
    match = re.search(r"```text\n(.*?)```", original.read_text(encoding="utf-8"), flags=re.S)
    return match.group(1).rstrip("\n") if match else ""


class Book:
    """The book's recipes and their review state, read fresh on every request."""

    def __init__(self, root: config.BookRoot) -> None:
        self.root = root
        self.log = root.book / "sources" / REVIEW_LOG

    def folders(self) -> list[Path]:
        return sorted(p.parent for p in (self.root.book / "recipes").glob("*/*/recipe.md"))

    def key(self, folder: Path) -> str:
        return folder.relative_to(self.root.book).as_posix()

    def folder(self, key: str) -> Path:
        folder = (self.root.book / key).resolve()
        if not folder.is_relative_to((self.root.book / "recipes").resolve()) or not (folder / "recipe.md").exists():
            raise KeyError(key)
        return folder

    def approvals(self) -> dict[str, str]:
        """Entry -> the recipe.md hash it was last approved at."""
        return {r["entry"]: r["sha"] for r in _records(self.log)}

    def ingested(self) -> dict[str, dict]:
        """Entry -> its latest `cookbook ingest` record (CHECK and NOTE lines)."""
        return {r["entry"]: r for r in _records(self.root.book / "sources" / models.LOG_NAME)
                if r.get("command") == "ingest"}

    def queue(self, everything: bool) -> list[dict]:
        approved = self.approvals()
        out = []
        for folder in self.folders():
            key = self.key(folder)
            text = (folder / "recipe.md").read_text(encoding="utf-8")
            done = approved.get(key) == _sha(text)
            original = (folder / "sources" / "recipe-original.md").exists()
            if everything or (not done and original):
                title = next((l[2:] for l in text.splitlines() if l.startswith("# ")), folder.name)
                out.append({"entry": key, "title": title, "approved": done, "original": original})
        return out

    def problems(self, folder: Path, text: str) -> dict:
        """Lint's checks and the audit's content checks on the entry as saved."""
        from . import audit, lint, render  # render needs the active root

        rep = lint.Report()
        lint.check_entry(rep, folder, "recipe.md", "recipe-original.md")
        lint.check_recipe_body(rep, folder, text)
        r = render.Recipe(folder.parent.name, folder.name, "", "")
        render.parse_recipe(r)
        content = [{"severity": f.severity, "check": f.check, "message": f.message}
                   for f in audit.entry_findings(r, text, config.load(self.root).estimates)]
        return {"errors": rep.errors, "warnings": rep.warnings, "content": content}

    def entry(self, key: str) -> dict:
        folder = self.folder(key)
        text = (folder / "recipe.md").read_text(encoding="utf-8")
        record = self.ingested().get(key, {})
        sources = folder / "sources"
        images = sorted(p for p in sources.iterdir() if p.suffix.lower() in IMAGE_TYPES) if sources.is_dir() else []
        return {
            "entry": key, "recipe": text, "verbatim": verbatim(folder),
            "images": [f"/file/{self.key(folder)}/sources/{p.name}" for p in images],
            "checks": record.get("checks", []), "notes": record.get("notes", []),
            "approved": self.approvals().get(key) == _sha(text),
            **self.problems(folder, text),
        }

    def save(self, key: str, text: str) -> tuple[Path, bool]:
        folder = self.folder(key)
        text = text.replace("\r\n", "\n").rstrip("\n") + "\n"
        md = folder / "recipe.md"
        edited = md.read_text(encoding="utf-8") != text
        if edited:
            md.write_text(text, encoding="utf-8")
        return folder, edited

    def approve(self, key: str, text: str, seconds: float, edited_before: bool) -> dict:
        folder, edited = self.save(key, text)
        text = (folder / "recipe.md").read_text(encoding="utf-8")
        found = self.problems(folder, text)
        if found["errors"]:
            return {"ok": False, **found}
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "date": dt.datetime.now().isoformat(timespec="seconds"), "entry": key,
                "seconds": round(seconds), "edited": edited or edited_before, "sha": _sha(text),
            }) + "\n")
        return {"ok": True, **found}

    def stats(self) -> dict:
        """The first approval of each recipe ingest wrote: what the target is measured on."""
        ingested = self.ingested()
        first: dict[str, dict] = {}
        for r in _records(self.log):
            if r["entry"] in ingested:
                first.setdefault(r["entry"], r)
        seconds = [r["seconds"] for r in first.values()]
        return {
            "reviewed": len(first), "edited": sum(r["edited"] for r in first.values()),
            "average_seconds": round(sum(seconds) / len(seconds)) if seconds else None,
            "target_seconds": TARGET_SECONDS,
        }


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(round(seconds), 60)
    return (f"{m} min {s} s" if s else f"{m} min") if m else f"{s} s"


def report(root: config.BookRoot) -> int:
    s = Book(root).stats()
    if not s["reviewed"]:
        print("No ingested recipe has been approved yet: run cookbook review.")
        return 0
    verdict = "under" if s["average_seconds"] < TARGET_SECONDS else "over"
    print(f"Reviewed {s['reviewed']} ingested recipe(s); {s['edited']} needed edits.")
    print(f"Average review time {_duration(s['average_seconds'])} per recipe — "
          f"{verdict} the {_duration(TARGET_SECONDS)} target.")
    return 0


class Handler(BaseHTTPRequestHandler):
    book: Book
    everything: bool

    def log_message(self, *args) -> None:  # the terminal shows the URL, not every request
        pass

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    def do_GET(self) -> None:
        url = urlparse(self.path)
        try:
            if url.path == "/":
                self._send(HTTPStatus.OK, PAGE.encode(), "text/html; charset=utf-8")
            elif url.path == "/api/queue":
                cfg = config.load(self.book.root)
                self._json({"title": cfg.title, "queue": self.book.queue(self.everything), **self.book.stats()})
            elif url.path == "/api/entry":
                self._json(self.book.entry(parse_qs(url.query)["e"][0]))
            elif url.path.startswith("/file/"):
                path = (self.book.root.book / unquote(url.path[len("/file/"):])).resolve()
                if not path.is_relative_to(self.book.root.book.resolve()) or path.suffix.lower() not in IMAGE_TYPES:
                    raise KeyError(url.path)
                self._send(HTTPStatus.OK, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/jpeg")
            else:
                raise KeyError(url.path)
        except (KeyError, TypeError, ValueError, FileNotFoundError):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/save":
                folder, edited = self.book.save(body["entry"], body["text"])
                text = (folder / "recipe.md").read_text(encoding="utf-8")
                self._json({"ok": True, "edited": edited, **self.book.problems(folder, text)})
            elif self.path == "/api/approve":
                self._json(self.book.approve(body["entry"], body["text"], float(body["seconds"]),
                                             bool(body.get("edited"))))
            else:
                raise KeyError(self.path)
        except (KeyError, TypeError, ValueError):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def main(root: config.BookRoot, *, port: int = 8765, everything: bool = False, open_browser: bool = True) -> int:
    book = Book(root)
    if not book.queue(everything):
        if not any((f / "sources" / "recipe-original.md").exists() for f in book.folders()):
            print("No ingested recipes to review: hand-written recipes have no original to check "
                  "against (--all opens every recipe anyway).")
        else:
            print("Nothing to review: every recipe with an original is approved (--all shows them all).")
        return 0
    handler = type("BookHandler", (Handler,), {"book": book, "everything": everything})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Reviewing {root.path.name} at {url} — Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return report(root)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review recipes</title>
<style>
  :root {
    --paper: #faf7f2; --ink: #2a2622; --muted: #6b635b; --rule: #e2dbd1;
    --accent: #8a5a2b; --check: #9a4a12; --check-bg: #fbeee2; --ok: #2f6b3f; --ok-bg: #e7f2e9;
    --error: #a3271f; --error-bg: #fbe9e7;
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); background: var(--paper);
  }
  * { box-sizing: border-box; }
  body { margin: 0; display: grid; grid-template-columns: 17rem 1fr; min-height: 100vh; }
  nav { border-right: 1px solid var(--rule); padding: 1rem; overflow-y: auto; max-height: 100vh; position: sticky; top: 0; }
  nav h1 { font-size: 1rem; margin: 0 0 .25rem; }
  .stats { color: var(--muted); font-size: .85rem; margin: 0 0 1rem; }
  nav ol { list-style: none; margin: 0; padding: 0; }
  nav button { all: unset; display: flex; gap: .5rem; width: 100%; padding: .35rem .5rem; border-radius: 6px; cursor: pointer; }
  nav button:hover, nav button:focus-visible { background: #efe8de; outline: 2px solid transparent; }
  nav button:focus-visible { box-shadow: 0 0 0 2px var(--accent); }
  nav button[aria-current="true"] { background: #e9dfd2; font-weight: 600; }
  nav .state { margin-left: auto; font-size: .75rem; color: var(--ok); }
  main { padding: 1rem 1.25rem 6rem; min-width: 0; }
  header h2 { margin: 0; font-size: 1.4rem; }
  header p { margin: .15rem 0 .75rem; color: var(--muted); font-size: .85rem; }
  .flags { display: grid; gap: .35rem; margin: 0 0 1rem; padding: 0; list-style: none; }
  .flags li { padding: .4rem .6rem; border-radius: 6px; font-size: .9rem; }
  .flags .check { background: var(--check-bg); color: var(--check); }
  .flags .note { background: #f1ede7; color: var(--muted); }
  .flags .error { background: var(--error-bg); color: var(--error); }
  .flags b { font-weight: 700; margin-right: .35rem; letter-spacing: .03em; font-size: .75rem; }
  .cols { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; align-items: start; }
  section h3 { font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 0 0 .4rem; }
  .pages a { display: block; margin-bottom: .5rem; }
  .pages img { width: 100%; border: 1px solid var(--rule); border-radius: 4px; background: #fff; }
  pre, textarea { font: 13px/1.55 ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
  pre { margin: 0; white-space: pre-wrap; background: #fff; border: 1px solid var(--rule); border-radius: 4px; padding: .75rem; }
  textarea { width: 100%; min-height: 70vh; resize: vertical; padding: .75rem; border: 1px solid var(--rule); border-radius: 4px; background: #fff; color: var(--ink); }
  textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
  footer { position: fixed; bottom: 0; left: 17rem; right: 0; display: flex; gap: .75rem; align-items: center;
           padding: .75rem 1.25rem; background: var(--paper); border-top: 1px solid var(--rule); }
  footer button { font: inherit; padding: .5rem 1rem; border-radius: 6px; border: 1px solid var(--accent); cursor: pointer; }
  footer button:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
  footer button:disabled { opacity: .45; cursor: default; }
  #save { background: #fff; color: var(--accent); }
  #approve { background: var(--accent); color: #fff; }
  #status { color: var(--muted); font-size: .9rem; }
  #status.ok { color: var(--ok); } #status.bad { color: var(--error); }
  kbd { font: .75rem ui-monospace, monospace; border: 1px solid var(--rule); border-radius: 3px; padding: 0 .25rem; }
  @media (max-width: 960px) {
    body { grid-template-columns: 1fr; }
    nav { position: static; max-height: none; border-right: 0; border-bottom: 1px solid var(--rule); }
    .cols { grid-template-columns: 1fr; }
    footer { left: 0; }
    textarea { min-height: 50vh; }
  }
  /* Inside the studio, which lists the recipes itself: the editor alone. */
  .embedded { grid-template-columns: 1fr; }
  .embedded nav { display: none; }
  .embedded footer { left: 0; }
</style>
</head>
<body>
<nav aria-label="Recipes to review">
  <h1 id="book"></h1>
  <p class="stats" id="stats"></p>
  <ol id="queue"></ol>
</nav>
<main>
  <header><h2 id="title">Loading…</h2><p id="path"></p></header>
  <ul class="flags" id="flags" aria-label="Flags"></ul>
  <div class="cols">
    <section aria-labelledby="h-pages"><h3 id="h-pages">Original</h3><div class="pages" id="pages"></div></section>
    <section aria-labelledby="h-verbatim"><h3 id="h-verbatim">Transcription</h3><pre id="verbatim"></pre></section>
    <section><h3><label for="recipe">recipe.md</label></h3><textarea id="recipe" spellcheck="true"></textarea></section>
  </div>
</main>
<footer>
  <button id="save" type="button" disabled>Save <kbd>Ctrl S</kbd></button>
  <button id="approve" type="button" disabled>Approve <kbd>Ctrl Enter</kbd></button>
  <span id="status" role="status" aria-live="polite"></span>
</footer>
<script>
const $ = (id) => document.getElementById(id);
let queue = [], current = null, shownAt = 0, activeMs = 0, edited = false;
let ingestFlags = { checks: [], notes: [] };  // what ingest flagged: kept while the entry is open

function clock() { if (shownAt) { activeMs += performance.now() - shownAt; shownAt = 0; } }
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clock(); else if (current) shownAt = performance.now();
});

function duration(s) {
  if (s == null) return "—";
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return m ? (r ? `${m} min ${r} s` : `${m} min`) : `${r} s`;
}

function setStatus(text, kind) { $("status").textContent = text; $("status").className = kind || ""; }

function flag(kind, label, text) {
  const li = document.createElement("li"); li.className = kind;
  const b = document.createElement("b"); b.textContent = label;
  li.append(b, document.createTextNode(text)); return li;
}

function showProblems(data) {
  data = { ...ingestFlags, ...data };
  const list = $("flags"); list.replaceChildren();
  for (const e of data.errors || []) list.append(flag("error", "ERROR", e));
  for (const c of data.checks || []) list.append(flag("check", "CHECK", c));
  for (const f of data.content || []) list.append(flag(f.severity === "note" ? "note" : f.severity === "error" ? "error" : "check", f.check.toUpperCase(), f.message));
  for (const w of data.warnings || []) list.append(flag("note", "LINT", w));
  for (const n of data.notes || []) list.append(flag("note", "NOTE", n));
}

async function loadQueue() {
  const data = await (await fetch("/api/queue")).json();
  queue = data.queue;
  $("book").textContent = data.title;
  const left = queue.filter((q) => !q.approved).length;
  $("stats").textContent = `${left} to review · ${data.reviewed} approved · average ${duration(data.average_seconds)} ` +
    `per recipe (target under ${duration(data.target_seconds)})`;
  const ol = $("queue"); ol.replaceChildren();
  for (const q of queue) {
    const li = document.createElement("li"), b = document.createElement("button");
    b.type = "button"; b.textContent = q.title; b.setAttribute("aria-current", String(q.entry === current));
    if (q.approved) { const s = document.createElement("span"); s.className = "state"; s.textContent = "Approved"; b.append(s); }
    b.onclick = () => open(q.entry);
    li.append(b); ol.append(li);
  }
}

async function open(entry) {
  clock();
  const data = await (await fetch("/api/entry?e=" + encodeURIComponent(entry))).json();
  current = entry; activeMs = 0; edited = false; shownAt = performance.now();
  $("save").disabled = $("approve").disabled = false;
  $("title").textContent = (data.recipe.match(/^# (.+)$/m) || [, entry])[1];
  $("path").textContent = "book/" + entry + (data.approved ? " · approved" : "");
  $("verbatim").textContent = data.verbatim || "No transcription: this recipe has no sources/recipe-original.md.";
  const pages = $("pages"); pages.replaceChildren();
  data.images.forEach((src, i) => {
    const a = document.createElement("a"); a.href = src; a.target = "_blank"; a.rel = "noopener";
    const img = document.createElement("img"); img.src = src; img.alt = `Original page ${i + 1}`;
    a.append(img); pages.append(a);
  });
  if (!data.images.length) pages.textContent = "No page images in sources/.";
  $("recipe").value = data.recipe;
  ingestFlags = { checks: data.checks, notes: data.notes };
  showProblems(data); setStatus("");
  await loadQueue();
}

async function post(url, extra) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entry: current, text: $("recipe").value, ...extra }) });
  return res.json();
}

async function save() {
  if (!current) return;
  const data = await post("/api/save");
  edited = edited || data.edited;
  showProblems(data);
  setStatus(data.errors.length ? "Saved, with errors to fix" : "Saved", data.errors.length ? "bad" : "ok");
}

async function approve() {
  if (!current) return;
  clock();
  const data = await post("/api/approve", { seconds: activeMs / 1000, edited });
  if (!data.ok) { showProblems(data); setStatus("Not approved: fix the errors first", "bad"); shownAt = performance.now(); return; }
  setStatus(`Approved after ${duration(activeMs / 1000)}`, "ok");
  await loadQueue();
  const next = queue.find((q) => !q.approved && q.entry !== current);
  if (next) open(next.entry);
  else {
    current = null; $("save").disabled = $("approve").disabled = true;
    setStatus("All recipes in the queue are approved.", "ok");
  }
}

$("save").onclick = save; $("approve").onclick = approve;
$("recipe").addEventListener("input", () => { edited = true; });
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); approve(); }
});

// The studio embeds this page with ?e=<entry>: open that recipe, without the queue beside it.
const asked = new URLSearchParams(location.search).get("e");
if (window.self !== window.top) document.body.classList.add("embedded");
loadQueue().then(() => {
  const first = queue.find((q) => q.entry === asked) || queue.find((q) => !q.approved) || queue[0];
  if (first) open(first.entry);
});
</script>
</body>
</html>
"""
