# Shorts Production Package + AI Lab Review Inbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every short ships to fal as a complete, owner-approved production package (scene bible, location plates, wardrobe, blocking, start/end keyframes, image-to-video), and every review in AI Lab goes through one inbox.

**Architecture:** A review *registry* (`tools/review/`) collects items from small producers into `items.json`; one static inbox page reads it plus the existing verdict store (`/designs/api/images`). The short model gains `[scene]`, `[wardrobe]`, `[blocking]` and per-shot `plate`/`mode`/`motion`/`end_frame`; pre-flight and the approval fingerprint cover them. Plates and keyframes render locally (ComfyUI, house NoobAI v-pred model) guided by grey-box lineart + per-character screen regions from Blender; fal gets Seedance 2.0 image-to-video.

**Tech Stack:** Python 3.12 stdlib + Pillow, pytest, ComfyUI API workflows (existing `tools.imagegen.build`), Blender 4.5 headless (Workbench), static HTML/JS, nginx (homelab-ops), fal queue API via httpx.

**Spec:** `docs/superpowers/specs/2026-11-10-shorts-production-package-design.md` (builds on `2026-11-09-shorts-production-sheet-design.md`).

## Global Constraints

- Work in the nightwire worktree `.claude/worktrees/shorts-test`, branch `feat/shorts-production-sheet` (rename not needed). AI Lab files are in the separate repo `homelab-ops` (`gpubox/`).
- Run tools with `export NIGHTWIRE_DESIGN_DIR=/home/sentinel/projects/github/repos/nightwire/design-data` and the venv python `../../../.venv/bin/python` (the worktree's own `design-data/` is empty).
- Tests: `../../../.venv/bin/python -m pytest tests/ -q` must stay green (1026 passed, 1 skipped at start).
- Never add `Co-Authored-By` or any AI-attribution trailer to commits. Never push without the owner's OK.
- Never read, print or log `FAL_KEY` (lives only in `~/.config/nightwire/secrets.env`). No paid fal call in any task; tests fake the backend.
- GPU box 192.168.10.19: one ComfyUI job at a time; free VRAM after a batch (`POST /svc/comfy/free {"unload_models":true,"free_memory":true}` on :8080 or `:8188/free`); never touch Ollama; run `python -m tools.taste` before a render batch. No downloads without the owner's OK.
- No daytime images; no explicit content. Night only.
- Review ids must match `[a-z0-9][a-z0-9-]{0,99}` (the verdict store rejects others). Separator inside ids is `--`.
- Verdict store: `GET/PUT/DELETE /designs/api/images/<id>` with `{"verdict": "keep"|"fix"|"reject"|"original", "note": ...}`. Picks: `/designs/api/picks/<slug>`.
- Do not size plans to the current fal balance (owner tops up). Still show costs and require per-shot approval.
- Plates/keyframes are reviewed in the inbox; never build a new ad-hoc review page.

## File map

| File | Responsibility |
|---|---|
| `tools/review/__init__.py` | package marker |
| `tools/review/registry.py` | `Item`, id validation, `web_copy`, `build_items`, `write_items` |
| `tools/review/producers.py` | one function per item kind (sheets, candidates, world, plans, takes, wallpapers, plates, scene, keyframes) |
| `tools/review/migrate.py` | copy old `reviews` verdicts into `images` as `sheet--…` ids |
| `tools/review/inbox.html` | the inbox page (template, no build step) |
| `tools/review/__main__.py` | `python -m tools.review build|migrate` |
| `tools/shorts/model.py` | `Scene`, wardrobe, blocking, shot plate/mode/motion/end_frame/changes |
| `tools/shorts/plates.py` | plate catalogue per place, plate paths and ids, plate render jobs |
| `tools/shorts/prompt.py` | bible text, i2v prompt, plate as place ref |
| `tools/shorts/preflight.py` | new package checks |
| `tools/shorts/approve.py` | fingerprint covers mode, bible, keyframes; scene approval |
| `tools/shorts/backends/fal.py` | i2v models, i2v request body, blocked jobs |
| `tools/shorts/takes.py` | ledger `blocked` and `adjust` rows |
| `tools/shorts/greybox/blender_build.py` | guide renders (room-only, edges, regions.json) |
| `tools/shorts/guides.py` | turn grey-box guide renders into lineart + regions |
| `tools/shorts/keyframes.py` | keyframe workflow + candidate render + choose |
| `tools/shorts/sheet.py` + `sheet.html` | per-short page with stage tabs and gates |
| `tools/shorts/__main__.py` | new commands: `plates`, `guides`, `keyframes`, `ledger-sync` |
| `narrator/worlds/designs/mama-satos-izakaya.plates.toml` | izakaya plate catalogue |
| `narrator/worlds/shorts/saeko-rin-izakaya/*.toml` | pilot filled with the new fields |
| homelab-ops `gpubox/dashboard/index.html`, `gpubox/nginx/nginx.conf`, `gpubox/dashboard/pipeline/index.html` | dashboard regroup, `/review/` location, how-to page |
| nightwire `CLAUDE.md` | registry rule |

---

## Phase A — Review inbox

### Task 1: Registry core

**Files:**
- Create: `tools/review/__init__.py` (empty), `tools/review/registry.py`
- Test: `tests/test_review_registry.py`

**Interfaces:**
- Produces: `Item(id, kind, stage, project, title, files, compare=[], context="", choices=("keep","fix","reject"), extra={})`; `STAGES = ("designs","pre-production","production","finished")`; `valid_id(s) -> bool`; `web_copy(src: Path, site: Path, rel: str, max_side=2048) -> str` (returns URL `/review/media/<rel>`); `build_items(producers, ctx) -> tuple[list[Item], list[str]]` (items, errors); `write_items(items, site: Path) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_registry.py
import json

import pytest
from PIL import Image

from tools.review.registry import Item, build_items, valid_id, web_copy, write_items


def test_valid_id():
    assert valid_id("plate--mama-satos-izakaya--toward-door")
    assert not valid_id("Plate--x") and not valid_id("") and not valid_id("a" * 101) and not valid_id("a_b")


def test_item_rejects_bad_id_and_stage():
    with pytest.raises(ValueError):
        Item("Bad Id", "plate", "pre-production", "p", "t", ["/x.jpg"])
    with pytest.raises(ValueError):
        Item("ok-id", "plate", "later", "p", "t", ["/x.jpg"])


def test_build_items_collects_and_keeps_going_on_error():
    def good(ctx):
        return [Item("a", "plate", "pre-production", "p", "A", ["/a.jpg"])]

    def broken(ctx):
        raise RuntimeError("boom")

    items, errors = build_items([good, broken], {})
    assert [i.id for i in items] == ["a"] and errors == ["broken: boom"]


def test_duplicate_ids_are_an_error():
    def twice(ctx):
        return [Item("a", "plate", "designs", "p", "A", ["/a.jpg"])] * 2

    items, errors = build_items([twice], {})
    assert len(items) == 1 and any("duplicate id a" in e for e in errors)


def test_web_copy_and_write(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (4000, 1000), "red").save(src)
    url = web_copy(src, tmp_path / "site", "plates/x.jpg")
    assert url == "/review/media/plates/x.jpg"
    assert max(Image.open(tmp_path / "site" / "media" / "plates" / "x.jpg").size) == 2048
    path = write_items([Item("a", "plate", "designs", "p", "A", [url])], tmp_path / "site")
    data = json.loads(path.read_text())
    assert data["items"][0]["id"] == "a" and data["items"][0]["choices"] == ["keep", "fix", "reject"]
```

- [ ] **Step 2: Run to verify failure**

Run: `../../../.venv/bin/python -m pytest tests/test_review_registry.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'tools.review'`

- [ ] **Step 3: Implement**

```python
# tools/review/registry.py
"""Everything the owner reviews in AI Lab, as one list. Producers (producers.py) each return Items for one kind of
work; the inbox page reads the list plus the shared verdict store (/designs/api/images). A new kind of work needs a
producer, never a new review page."""

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

STAGES = ("designs", "pre-production", "production", "finished")
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")  # same rule as the verdict store (tools/design_picks.py _IMAGE_ID)


def valid_id(s: str) -> bool:
    return bool(_ID.fullmatch(s))


@dataclass
class Item:
    id: str
    kind: str
    stage: str
    project: str
    title: str
    files: list[str]                                  # URLs of what is judged (image or video)
    compare: list[dict] = field(default_factory=list)  # [{"label": ..., "url": ...}] shown beside it
    context: str = ""                                  # prompt, bible, notes
    choices: tuple = ("keep", "fix", "reject")
    extra: dict = field(default_factory=dict)         # kind-specific data the page understands (e.g. pick rounds)

    def __post_init__(self):
        if not valid_id(self.id):
            raise ValueError(f"review id {self.id!r} must match {_ID.pattern}")
        if self.stage not in STAGES:
            raise ValueError(f"stage {self.stage!r} not in {STAGES}")


def web_copy(src: Path, site: Path, rel: str, max_side: int = 2048) -> str:
    """A JPEG no longer than max_side under site/media/rel; returns its URL. Skips work when the copy is newer."""
    from PIL import Image
    out = site / "media" / rel
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        out.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(src).convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(out, "JPEG", quality=88)
    return f"/review/media/{rel}"


def build_items(producers, ctx: dict) -> tuple[list[Item], list[str]]:
    items, errors, seen = [], [], set()
    for p in producers:
        try:
            got = p(ctx)
        except Exception as e:  # one broken producer must not hide every other review
            errors.append(f"{p.__name__}: {e}")
            continue
        for it in got:
            if it.id in seen:
                errors.append(f"{p.__name__}: duplicate id {it.id}")
                continue
            seen.add(it.id)
            items.append(it)
    return items, errors


def write_items(items: list[Item], site: Path) -> Path:
    site.mkdir(parents=True, exist_ok=True)
    path = site / "items.json"
    rows = [{**asdict(i), "choices": list(i.choices)} for i in items]
    path.write_text(json.dumps({"built": dt.datetime.now().isoformat(timespec="seconds"), "items": rows}, indent=1))
    return path
```

- [ ] **Step 4: Run tests** — `../../../.venv/bin/python -m pytest tests/test_review_registry.py -q` → PASS
- [ ] **Step 5: Commit** — `git add tools/review tests/test_review_registry.py && git commit -m "review: item registry"`

### Task 2: Producers for the kinds that exist today

**Files:**
- Create: `tools/review/producers.py`
- Test: `tests/test_review_producers.py`

**Interfaces:**
- Consumes: `Item`, `web_copy` (Task 1); `narrator.designs.load_designs()`; `tools.design_studio.CHARACTER_SHEETS` is not needed — use the sheet names below.
- Produces: producer functions taking `ctx` dict with keys `design_dir: Path` (design-data), `site: Path` (review/_site), `world_ids: Path | None`, `shorts_site: Path` (design-data/shorts/_site), `designs: dict`:
  `sheets(ctx)`, `candidates(ctx)`, `world(ctx)`, `takes(ctx)`, `wallpapers(ctx)`. Id helpers: `sheet_id(slug, version) -> "sheet--<slug>--<version>"`.
  `ALL = [sheets, candidates, world, takes, wallpapers]` (Tasks 8, 12, 15 append plates, scene/plans, keyframes).

Sheet version must equal what `tools/design_studio._review_page` computes: `str(max(mtime_ns of existing sheet pngs))`, so migrated verdicts line up.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_producers.py
import json
from types import SimpleNamespace

from PIL import Image

from tools.review import producers as P


def png(path, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "blue").save(path)
    return path


def ctx(tmp_path, designs=None, world=None):
    return {"design_dir": tmp_path / "dd", "site": tmp_path / "site", "world_ids": world,
            "shorts_site": tmp_path / "dd" / "shorts" / "_site", "designs": designs or {}}


def char(slug, status="approved"):
    return SimpleNamespace(slug=slug, name=slug.title(), kind="character", status=status)


def test_sheets_one_item_per_character_with_old_versions_as_compare(tmp_path):
    c = ctx(tmp_path, {"saeko": char("saeko"), "draft": char("draft", "draft")})
    png(c["design_dir"] / "saeko" / "turnaround.png")
    png(c["design_dir"] / "saeko" / "turnaround-old.png")
    png(c["design_dir"] / "saeko" / "portrait.png")
    png(c["design_dir"] / "draft" / "turnaround.png")
    (item,) = P.sheets(c)
    assert item.kind == "sheet" and item.stage == "designs" and item.project == "saeko"
    assert item.id.startswith("sheet--saeko--") and len(item.files) == 2
    assert [x["label"] for x in item.compare] == ["Turnaround: before"]


def test_candidates_from_gallery_rounds(tmp_path):
    c = ctx(tmp_path)
    g = c["design_dir"] / "gallery"
    png(g / "img" / "rin" / "r2-c1.jpg"); png(g / "img" / "rin" / "r2-c2.jpg")
    (g / "rounds.json").write_text(json.dumps({"rin": 2}))
    (item,) = P.candidates(c)
    assert item.kind == "pick" and item.choices == ("pick", "reroll", "skip")
    assert item.extra == {"slug": "rin", "round": 2, "n": [1, 2]}
    assert item.files == ["/designs/img/rin/r2-c1.jpg", "/designs/img/rin/r2-c2.jpg"]


def test_world_takes_wallpapers(tmp_path):
    ids = tmp_path / "ids.json"
    ids.write_text(json.dumps(["cast-rin"]))
    c = ctx(tmp_path, world=ids)
    (w,) = P.world(c)
    assert w.id == "cast-rin" and w.files == ["/world/cast-rin.jpg"] and w.stage == "production"
    site = c["shorts_site"]
    site.mkdir(parents=True)
    (site / "shorts.json").write_text(json.dumps([{"slug": "pilot", "title": "Resting", "shots": [
        {"id": "S01", "takes": [{"id": "t001", "image_id": "short--pilot--s01--t001", "src": "pilot/S01/takes/t001.mp4"}]}]}]))
    (t,) = P.takes(c)
    assert t.id == "short--pilot--s01--t001" and t.files == ["/shorts/pilot/S01/takes/t001.mp4"] and t.project == "pilot"
    (site / "loops").mkdir()
    (site / "loops" / "loops.json").write_text(json.dumps({"wallpapers": [
        {"id": "loop--x", "file": "x.mp4", "title": "X", "note": "n"}], "experiments": []}))
    (wp,) = P.wallpapers(c)
    assert wp.id == "loop--x" and wp.files == ["/shorts/loops/x.mp4"] and wp.stage == "finished"
```

- [ ] **Step 2: Run** — `../../../.venv/bin/python -m pytest tests/test_review_producers.py -q` → FAIL (no module)
- [ ] **Step 3: Implement**

```python
# tools/review/producers.py
"""One function per kind of reviewable work. Each returns Items; registry.build_items collects them.
URLs point at pages already published on the AI Lab box (/designs, /world, /shorts) or at copies made with web_copy."""

import json
from pathlib import Path

from tools.review.registry import Item, web_copy

SHEETS = (("portrait", "Portrait"), ("expressions", "Expressions"), ("turnaround", "Turnaround"),
          ("colorguide", "Colour guide"), ("props", "Hands and props"))


def sheet_id(slug: str, version: str) -> str:
    return f"sheet--{slug}--{version}"


def sheets(ctx) -> list[Item]:
    out = []
    for slug, d in sorted(ctx["designs"].items()):
        folder = ctx["design_dir"] / slug
        now = [(s, t) for s, t in SHEETS if (folder / f"{s}.png").exists()]
        if d.kind != "character" or d.status != "approved" or not now:
            continue
        version = str(max((folder / f"{s}.png").stat().st_mtime_ns for s, _ in now))  # = design_studio._review_page
        files = [web_copy(folder / f"{s}.png", ctx["site"], f"sheets/{slug}/{s}.jpg") for s, _ in now]
        compare = [{"label": f"{t}: before", "url": web_copy(folder / f"{s}-old.png", ctx["site"], f"sheets/{slug}/{s}-old.jpg")}
                   for s, t in SHEETS if (folder / f"{s}-old.png").exists()]
        out.append(Item(sheet_id(slug, version), "sheet", "designs", slug, f"{d.name}: model sheets", files, compare))
    return out


def candidates(ctx) -> list[Item]:
    g = ctx["design_dir"] / "gallery"
    if not (g / "rounds.json").exists():
        return []
    out = []
    for slug, rnd in sorted(json.loads((g / "rounds.json").read_text()).items()):
        ns = sorted(int(p.stem.split("-c")[1]) for p in (g / "img" / slug).glob(f"r{rnd}-c*.jpg")
                    if p.stem.split("-c")[1].isdigit())
        if ns:
            out.append(Item(f"pick--{slug}--r{rnd}", "pick", "designs", slug, f"{slug}: pick a design (round {rnd})",
                            [f"/designs/img/{slug}/r{rnd}-c{n}.jpg" for n in ns], choices=("pick", "reroll", "skip"),
                            extra={"slug": slug, "round": rnd, "n": ns}))
    return out


def world(ctx) -> list[Item]:
    path = ctx.get("world_ids")
    if not path or not Path(path).exists():
        return []
    return [Item(i, "render", "production", "world", i.replace("-", " "), [f"/world/{i}.jpg"],
                 compare=[{"label": "Full size", "url": f"/world/{i}-full.jpg"}])
            for i in json.loads(Path(path).read_text())]


def takes(ctx) -> list[Item]:
    path = ctx["shorts_site"] / "shorts.json"
    if not path.exists():
        return []
    out = []
    for e in json.loads(path.read_text()):
        for shot in e.get("shots", []):
            for t in shot.get("takes", []):
                out.append(Item(t["image_id"], "take", "production", e["slug"], f"{e.get('title', e['slug'])} {shot['id']} {t['id']}",
                                [f"/shorts/{t['src']}"], context=t.get("note", "")))
    return out


def wallpapers(ctx) -> list[Item]:
    path = ctx["shorts_site"] / "loops" / "loops.json"
    if not path.exists():
        return []
    return [Item(w["id"], "wallpaper", "finished", "wallpapers", w["title"], [f"/shorts/loops/{w['file']}"],
                 context=w.get("note", "")) for w in json.loads(path.read_text())["wallpapers"]]


ALL = [sheets, candidates, world, takes, wallpapers]
```

- [ ] **Step 4: Run** — PASS. Then run the full suite.
- [ ] **Step 5: Commit** — `git commit -am "review: producers for sheets, picks, world, takes, wallpapers"` (add the new files first).

### Task 3: Migrate old sheet verdicts

**Files:**
- Create: `tools/review/migrate.py`
- Test: `tests/test_review_migrate.py`

**Interfaces:**
- Consumes: `sheet_id` (Task 2).
- Produces: `plan_migration(reviews: dict, images: dict) -> dict[str, dict]` — the PUT bodies to send, keyed by new id; skips ids already present in `images`. Verdict map: `ok → keep`, `fix → fix` (note kept). `run(api_base: str) -> int` does GET reviews, GET images, PUTs each with `Content-Type: application/json`, prints a count.

- [ ] **Step 1: Test**

```python
# tests/test_review_migrate.py
from tools.review.migrate import plan_migration


def test_plan_migration_maps_and_skips_existing():
    reviews = {"saeko": {"verdict": "ok", "v": "123", "note": ""},
               "rin": {"verdict": "fix", "v": "456", "note": "hair colour"},
               "old": {"verdict": "ok"}}  # no version: cannot be matched to a sheet set, skipped
    images = {"sheet--rin--456": {"verdict": "fix"}}
    assert plan_migration(reviews, images) == {"sheet--saeko--123": {"verdict": "keep"}}
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement**

```python
# tools/review/migrate.py
"""One-off: copy the old per-character sheet reviews (/designs/api/reviews) into the shared verdict store as
sheet--<slug>--<version>, so the inbox shows them as already reviewed. Safe to re-run: existing ids are left alone."""

import json
import urllib.request

from tools.review.producers import sheet_id
from tools.review.registry import valid_id

MAP = {"ok": "keep", "fix": "fix"}


def plan_migration(reviews: dict, images: dict) -> dict[str, dict]:
    out = {}
    for slug, r in reviews.items():
        v, verdict = str(r.get("v", "")), MAP.get(r.get("verdict", ""))
        new = sheet_id(slug, v)
        if not v or not verdict or not valid_id(new) or new in images:
            continue
        out[new] = {"verdict": verdict, **({"note": r["note"]} if verdict == "fix" and r.get("note") else {})}
    return out


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def run(api_base: str = "http://192.168.10.19:8080/designs/api") -> int:
    todo = plan_migration(_get(f"{api_base}/reviews"), _get(f"{api_base}/images"))
    for new, body in todo.items():
        req = urllib.request.Request(f"{api_base}/images/{new}", data=json.dumps(body).encode(), method="PUT",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    print(f"migrated {len(todo)} sheet review(s)")
    return 0
```

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `git add tools/review/migrate.py tests/test_review_migrate.py && git commit -m "review: migrate old sheet verdicts"`

### Task 4: Inbox page and `python -m tools.review`

**Files:**
- Create: `tools/review/inbox.html`, `tools/review/__main__.py`
- Test: `tests/test_review_cli.py`

**Interfaces:**
- Consumes: Tasks 1-3; `narrator.designs.load_designs`.
- Produces: `python -m tools.review build [--world-ids PATH]` → writes `design-data/review/_site/{index.html,items.json,media/…}` and prints the rsync line `rsync -a design-data/review/_site/ 192.168.10.19:anvil-deploy/stack/dashboard/review/`; `python -m tools.review migrate`. `main(argv) -> int`.
- The page: `?kind=<kind>` and `?project=<slug>` filters (old review tiles link here filtered).

- [ ] **Step 1: Test**

```python
# tests/test_review_cli.py
import json

from tools.review.__main__ import main


def test_build_writes_page_and_items(tmp_path, monkeypatch):
    dd = tmp_path / "dd"
    (dd / "shorts" / "_site").mkdir(parents=True)
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(dd))
    monkeypatch.setattr("tools.review.__main__.load_designs", lambda: {})
    assert main(["build"]) == 0
    site = dd / "review" / "_site"
    assert "items.json" in (site / "index.html").read_text()
    assert json.loads((site / "items.json").read_text())["items"] == []
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement `__main__.py`**

```python
# tools/review/__main__.py
"""python -m tools.review build [--world-ids PATH] | migrate"""

import argparse
import os
import sys
from pathlib import Path

from narrator.designs import load_designs
from tools.review import migrate, producers
from tools.review.registry import build_items, write_items

PAGE = Path(__file__).with_name("inbox.html")
REMOTE = "192.168.10.19:anvil-deploy/stack/dashboard/review/"


def design_dir() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--world-ids", type=Path, help="world-page/ids.json (default: the lab archive's, when present)")
    sub.add_parser("migrate")
    a = ap.parse_args(argv)
    if a.cmd == "migrate":
        return migrate.run()
    dd = design_dir()
    site = dd / "review" / "_site"
    world_ids = a.world_ids or next(iter(sorted(dd.glob("lab-archive/*/world-page/ids.json"))), None)
    ctx = {"design_dir": dd, "site": site, "world_ids": world_ids, "shorts_site": dd / "shorts" / "_site",
           "designs": load_designs()}
    items, errors = build_items(producers.ALL, ctx)
    write_items(items, site)
    (site / "index.html").write_text(PAGE.read_text())
    for e in errors:
        print(f"warning: {e}", file=sys.stderr)
    print(f"{len(items)} item(s); publish with:\nrsync -a {site}/ {REMOTE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement `inbox.html`** (complete file; no external scripts; dark/light tokens like the other AI Lab pages)

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review inbox</title>
<style>
:root{--bg:#0e1015;--card:#181b22;--fg:#e8e8ee;--dim:#9aa0ad;--ok:#3fb27f;--fix:#d9a03a;--no:#d0565b;--line:#2a2e38}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f4f4f6;--card:#fff;--fg:#16181d;--dim:#5b6070;--line:#dde0e6}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
main{max-width:1200px;margin:0 auto;padding:16px}
h1{margin:.2em 0} h2{margin:1.4em 0 .4em;font-size:1.1em;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
h3{margin:.8em 0 .3em;font-size:1em}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center} .bar select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.card img,.card video{width:100%;border-radius:6px;display:block;cursor:zoom-in}
.files{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:6px}
.kind{font-size:.75em;color:var(--dim);text-transform:uppercase}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px} .ctl input{flex:1 1 140px;min-width:0;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px}
button{border:0;border-radius:6px;padding:6px 10px;font-weight:600;cursor:pointer;color:#fff}
.keep,.pick{background:var(--ok)} .fix,.reroll{background:var(--fix)} .reject,.skip{background:var(--no)} .undo{background:var(--line);color:var(--fg)}
.state{font-size:.85em;color:var(--dim)} details{margin-top:6px} pre{white-space:pre-wrap;font-size:.8em;color:var(--dim)}
#full{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;overflow:auto;padding:16px;z-index:9}
#full.on{display:block} #full .row{display:flex;gap:10px;flex-wrap:wrap} #full figure{margin:0;flex:1 1 380px}
#full img,#full video{width:100%} #full figcaption{color:#ccc;font-size:.85em}
</style></head><body><main>
<h1>Review inbox</h1>
<p class="state">Everything waiting on you, in pipeline order. Click a picture to see it full size beside what it must match.</p>
<div class="bar"><label>Kind <select id="kind"><option value="">all</option></select></label>
<label>Project <select id="project"><option value="">all</option></select></label><span id="count" class="state"></span></div>
<div id="app"></div>
<div id="full" role="dialog" aria-modal="true"></div>
</main>
<script>
const API = "/designs/api/images", PICKS = "/designs/api/picks";
const STAGES = ["designs", "pre-production", "production", "finished"];
const NAMES = {"designs": "Designs", "pre-production": "Pre-production", "production": "Production", "finished": "Finished"};
let items = [], verdicts = {}, picks = {};
const q = new URLSearchParams(location.search);
const el = (t, a = {}, ...kids) => { const e = Object.assign(document.createElement(t), a); e.append(...kids); return e; };
const media = (url, full) => url.endsWith(".mp4")
  ? el("video", {src: url, controls: true, muted: true, loop: true, playsInline: true, preload: "metadata"})
  : el("img", {src: url, loading: "lazy", alt: ""});
const done = it => it.kind === "pick" ? !!picks[it.extra.slug] && picks[it.extra.slug].round === it.extra.round : !!verdicts[it.id];

async function load() {
  const [a, b, c] = await Promise.all([fetch("items.json").then(r => r.json()), fetch(API).then(r => r.json()),
                                       fetch(PICKS).then(r => r.json())]);
  items = a.items; verdicts = b; picks = c;
  for (const [id, key] of [["kind", "kind"], ["project", "project"]]) {
    const s = document.getElementById(id);
    for (const v of [...new Set(items.map(i => i[key]))].sort()) s.append(el("option", {value: v, textContent: v}));
    s.value = q.get(id) || ""; s.onchange = () => { q.set(id, s.value); history.replaceState(null, "", "?" + q); render(); };
  }
  render();
}

async function send(url, method, body) {
  const r = await fetch(url, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function open(it) {
  const f = document.getElementById("full"); f.textContent = "";
  const row = el("div", {className: "row"});
  for (const u of it.files) row.append(el("figure", {}, media(u), el("figcaption", {textContent: it.title})));
  for (const c of it.compare) row.append(el("figure", {}, media(c.url), el("figcaption", {textContent: c.label})));
  f.append(el("button", {className: "undo", textContent: "Close (Esc)", onclick: () => f.classList.remove("on")}), row);
  if (it.context) f.append(el("pre", {textContent: it.context}));
  f.classList.add("on");
}
document.addEventListener("keydown", e => { if (e.key === "Escape") document.getElementById("full").classList.remove("on"); });

function controls(it) {
  const st = el("span", {className: "state", role: "status"});
  const note = el("input", {type: "text", maxLength: 500, placeholder: it.kind === "pick" ? "Note for a reroll" : "What needs fixing?"});
  const box = el("div", {className: "ctl"});
  const act = async (fn, msg) => { try { await fn(); st.textContent = msg; render(); } catch (e) { st.textContent = "Not saved: " + e.message; } };
  if (it.kind === "pick") {
    it.extra.n.forEach((n, i) => box.append(el("button", {className: "pick", textContent: `Pick ${i + 1}`, onclick: () => act(async () => {
      picks = await send(`${PICKS}/${it.extra.slug}`, "PUT", {action: "pick", n, round: it.extra.round}); }, "Saved")})));
    box.append(note, el("button", {className: "reroll", textContent: "Reroll", onclick: () => act(async () => {
      picks = await send(`${PICKS}/${it.extra.slug}`, "PUT", {action: "reroll", note: note.value}); }, "Saved")}));
  } else {
    const put = v => act(async () => { verdicts = await send(`${API}/${it.id}`, "PUT", v === "fix" ? {verdict: v, note: note.value} : {verdict: v}); }, "Saved");
    box.append(el("button", {className: "keep", textContent: "Keep", onclick: () => put("keep")}), note,
               el("button", {className: "fix", textContent: "Needs a fix", onclick: () => { if (!note.value.trim()) { st.textContent = "Say what to fix first."; return; } put("fix"); }}),
               el("button", {className: "reject", textContent: "Reject", onclick: () => put("reject")}));
  }
  if (done(it)) box.append(el("button", {className: "undo", textContent: "Undo", onclick: () => act(async () => {
    if (it.kind === "pick") picks = await send(`${PICKS}/${it.extra.slug}`, "DELETE"); else verdicts = await send(`${API}/${it.id}`, "DELETE"); }, "Undone")}));
  box.append(st);
  return box;
}

function card(it) {
  const v = verdicts[it.id];
  const files = el("div", {className: "files"});
  it.files.slice(0, 6).forEach(u => { const m = media(u); m.onclick = () => open(it); files.append(m); });
  const c = el("div", {className: "card"}, el("div", {className: "kind", textContent: `${it.kind} · ${it.project}`}),
               el("h3", {textContent: it.title}), files);
  if (v) c.append(el("p", {className: "state", textContent: `Your answer: ${v.verdict}${v.note ? " — " + v.note : ""}`}));
  if (it.context) c.append(el("details", {}, el("summary", {textContent: "Details"}), el("pre", {textContent: it.context})));
  c.append(controls(it));
  return c;
}

function render() {
  const app = document.getElementById("app"); app.textContent = "";
  const shown = items.filter(i => (!q.get("kind") || i.kind === q.get("kind")) && (!q.get("project") || i.project === q.get("project")));
  const todo = shown.filter(i => !done(i));
  document.getElementById("count").textContent = `${todo.length} waiting on you`;
  for (const s of STAGES) {
    const mine = todo.filter(i => i.stage === s);
    if (!mine.length) continue;
    app.append(el("h2", {textContent: `${NAMES[s]} · ${mine.length}`}));
    for (const p of [...new Set(mine.map(i => i.project))]) {
      const grid = el("div", {className: "grid"}); mine.filter(i => i.project === p).forEach(i => grid.append(card(i)));
      app.append(el("h3", {textContent: p}), grid);
    }
  }
  const old = shown.filter(done);
  if (old.length) {
    const grid = el("div", {className: "grid"}); old.forEach(i => grid.append(card(i)));
    app.append(el("details", {}, el("summary", {textContent: `Reviewed · ${old.length}`}), grid));
  }
}
load().catch(e => { document.getElementById("app").textContent = "Couldn't load the inbox: " + e.message; });
</script></body></html>
```

- [ ] **Step 5: Run test** → PASS; full suite green.
- [ ] **Step 6: Commit** — `git add tools/review tests/test_review_cli.py && git commit -m "review: inbox page and build command"`

### Task 5: AI Lab wiring (homelab-ops) + rule in nightwire CLAUDE.md

**Files (homelab-ops repo):**
- Modify: `gpubox/nginx/nginx.conf` — add after the `/shorts/` location:

```nginx
    # Review inbox (static; verdicts go to /designs/api/images and /designs/api/picks).
    location /review/ {
        root /usr/share/nginx/html;
        index index.html;
        add_header Cache-Control "no-cache";
        try_files $uri $uri/ =404;
    }
```

- Modify: `gpubox/dashboard/index.html` — replace the sections "Waiting on you", "1. Pre-production", "2. Production", "3. Finished" (lines ~140-236) with five sections, keeping the existing tile markup/classes:
  - **Review**: one tile "Review inbox" → `/review/` with a badge = count of items in `/review/items.json` whose id is not in `/designs/api/images` (and, for `kind == "pick"`, whose slug has no pick for that round in `/designs/api/picks`). Replace the old badge scripts that counted `/world/ids.json`, sheet versions and plan ids with this one count.
  - **Productions**: one tile per short from `/shorts/shorts.json` → `/shorts/<slug>/` showing the short's title (stage label comes in Task 14; until then link `/shorts/<slug>/sheet/`).
  - **Make**: Image Studio (`/studio/`), Characters and places (`/designs/`).
  - **Library** (browse only): Approved art (`/approved/`), Final cuts and takes (`/shorts/`), Live wallpapers (`/shorts/loops/`).
  - **Machine**: existing "GPU and queue", "Recent renders", "Tools", "Services" sections unchanged.
  - Add a small link "How the pipeline works" → `/pipeline/`.
- Create: `gpubox/dashboard/pipeline/index.html` — a plain page (same tokens as inbox) explaining, in order: Designs (pick → sheets) → Short pre-production (scene bible → plates → keyframes → shot plans) → Production (takes on fal) → Finished (cut, wallpapers); "every decision is in the Review inbox; nothing is paid for until its shot is approved; a shot's approval breaks when anything it depends on changes".
- Old review pages: add one line at the top of `/designs/review/` template (`nightwire tools/design_review.html`) and the world gallery (`homelab-ops gpubox/world/gen_world.py` page header) — `<p>Reviews now live in the <a href="/review/?kind=sheet">Review inbox</a>.</p>` (kind `render` for world). Their buttons stay working until the inbox has been used for a week (owner decides removal).

**Files (nightwire):**
- Modify: `CLAUDE.md` — append:

```markdown
## AI Lab reviews

Every output the owner reviews goes through the review registry (`tools/review/`): add a producer in
`tools/review/producers.py` that returns `Item`s, rebuild with `python -m tools.review build`, publish with the printed
rsync. Never build a separate review page. Verdicts live in the shared store `/designs/api/images` (picks in
`/designs/api/picks`).
```

- [ ] **Step 1:** Make the edits. Validate nginx syntax on the box: `ssh 192.168.10.19 'cd anvil-deploy/stack && docker compose exec -T nginx nginx -t'` after copying the conf (path per homelab-ops README "gpubox" section); reload with `nginx -s reload`.
- [ ] **Step 2:** Back up the live dashboard first: `ssh 192.168.10.19 'cp anvil-deploy/stack/dashboard/index.html anvil-deploy/stack/dashboard/index.html.bak-20261110-inbox'`, then `scp` index.html and `pipeline/`.
- [ ] **Step 3:** Run `python -m tools.review migrate` once, then `python -m tools.review build` and the printed rsync.
- [ ] **Step 4: Verify** — `curl -s -o /dev/null -w "%{http_code}" http://192.168.10.19:8080/review/` = 200; `curl -s http://192.168.10.19:8080/review/items.json | python3 -c "import json,sys;print(len(json.load(sys.stdin)['items']))"` > 0; open the page in a browser (Claude in Chrome), Keep then Undo one wallpaper item and confirm `GET /designs/api/images` reflects both.
- [ ] **Step 5: Commit** both repos (homelab-ops: `AI Lab: review inbox, regrouped dashboard, pipeline page`; nightwire: `docs: review registry rule`). Do not push.

## Phase B — Package data and checks

### Task 6: Model fields

**Files:**
- Modify: `tools/shorts/model.py`
- Test: `tests/test_shorts_model.py` (append)

**Interfaces:**
- Produces: `Scene(time, weather, set, light: list[str], not_visible: list[str])`; `Short.scene: Scene | None`, `Short.wardrobe: dict[str,str]`, `Short.blocking: dict[str,str]`; `Shot.plate: str`, `Shot.mode: str` (`"i2v"` default, or `"reference"`), `Shot.motion: str`, `Shot.end_frame: bool`, `Shot.wardrobe_change: list[str]`, `Shot.blocking_change: bool`. `MODES = ("i2v", "reference")`. `scene_text(short) -> str` (the bible as sent).

- [ ] **Step 1: Tests** (append to `tests/test_shorts_model.py`; reuse its `SHORT`, `PLANNED`, `write`, `designs`):

```python
SCENE = '''
[scene]
time = "late night"
weather = "indoors; no windows"
set = "a narrow izakaya"
light = ["paper lanterns", "red neon sign"]
not_visible = ["windows", "rain"]

[wardrobe]
C1 = "navy jacket zipped"

[blocking]
seating = "side by side"
'''


def test_scene_wardrobe_blocking_and_shot_package_fields(tmp_path):
    from tools.shorts.model import scene_text
    shot = PLANNED + '\nplate = "toward-door"\nmotion = "C2 turns."\nend_frame = true\n'
    s = load_short(write(tmp_path, short=SHORT + SCENE, shot=shot))
    assert s.scene.light == ["paper lanterns", "red neon sign"] and s.wardrobe["C1"] == "navy jacket zipped"
    assert s.blocking["seating"] == "side by side"
    sh = s.shots[0]
    assert (sh.plate, sh.mode, sh.motion, sh.end_frame) == ("toward-door", "i2v", "C2 turns.", True)
    t = scene_text(s)
    assert "Time: late night." in t and "Not visible: windows, rain." in t and "Light: paper lanterns; red neon sign." in t


def test_validate_rejects_bad_mode_and_unknown_wardrobe_id(tmp_path):
    shot = PLANNED + '\nmode = "dream"\nwardrobe_change = ["C9"]\n'
    s = load_short(write(tmp_path, short=SHORT + SCENE.replace('C1 = "navy', 'C7 = "navy'), shot=shot))
    p = validate_short(s, designs())
    assert any("mode 'dream'" in x for x in p) and any("unknown cast id C9" in x for x in p)
    assert any("wardrobe: unknown cast id C7" in x for x in p)
```

(If `write` lacks a `short=` parameter, add one to it: `def write(tmp_path, short=SHORT, shot=SHOT)` writing `short` to `short.toml`.)

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** in `model.py`:

```python
MODES = ("i2v", "reference")


@dataclass
class Scene:
    time: str
    weather: str
    set: str
    light: list[str]
    not_visible: list[str]


def scene_text(short) -> str:
    """The scene bible exactly as every shot sends it."""
    s = short.scene
    if s is None:
        return ""
    return " ".join([f"Time: {s.time}.", f"Weather: {s.weather}.", f"Set: {s.set}.",
                     f"Light: {'; '.join(s.light)}." if s.light else "",
                     f"Not visible: {', '.join(s.not_visible)}." if s.not_visible else ""]).strip()
```

Add to `Shot`: `plate: str = ""`, `mode: str = "i2v"`, `motion: str = ""`, `end_frame: bool = False`, `wardrobe_change: list[str] = field(default_factory=list)`, `blocking_change: bool = False`; read them in `_shot` with `d.get(...)` (lists via `list(...)`). Add to `Short`: `scene: Scene | None = None`, `wardrobe: dict[str, str] = field(default_factory=dict)`, `blocking: dict[str, str] = field(default_factory=dict)`; in `load_short`: `scene=Scene(**{"light": [], "not_visible": [], **d["scene"]}) if "scene" in d else None`, `wardrobe=dict(d.get("wardrobe", {}))`, `blocking=dict(d.get("blocking", {}))`. In `validate_short`: `for cid in s.wardrobe: if cid not in s.cast: problems.append(f"wardrobe: unknown cast id {cid}")`; per shot: `if shot.mode not in MODES: problems.append(f"{where}: mode {shot.mode!r} not in {MODES}")`, add `shot.wardrobe_change` to `ids`, and `if not isinstance(shot.end_frame, bool) or not isinstance(shot.blocking_change, bool): problems.append(f"{where}: end_frame and blocking_change must be true or false")`.

- [ ] **Step 4: Run** → PASS; full suite.
- [ ] **Step 5: Commit** — `git commit -am "shorts: scene bible, wardrobe, blocking, per-shot package fields"`

### Task 7: Plate catalogue

**Files:**
- Create: `tools/shorts/plates.py`, `narrator/worlds/designs/mama-satos-izakaya.plates.toml`
- Test: `tests/test_shorts_plates.py`

**Interfaces:**
- Produces: `Plate(name, view, source="")`; `load_plates(place: str, designs_root: Path = DESIGNS_ROOT) -> dict[str, Plate]` (empty dict when no file); `plate_path(design_dir, place, name) -> Path` = `design_dir/place/plates/<name>.png`, or `design_dir/place/<source>` when `source` is set; `plate_id(place, name) -> "plate--<place>--<name>"`. `DESIGNS_ROOT = Path("narrator/worlds/designs")`.

- [ ] **Step 1: Test**

```python
# tests/test_shorts_plates.py
from tools.shorts.plates import load_plates, plate_id, plate_path

TOML = '''
[[plate]]
name = "toward-shelves"
view = "from the stools toward the shelves"
source = "play.png"
[[plate]]
name = "toward-door"
view = "from behind the counter toward the noren door"
'''


def test_load_and_paths(tmp_path):
    (tmp_path / "izakaya.plates.toml").write_text(TOML)
    p = load_plates("izakaya", tmp_path)
    assert list(p) == ["toward-shelves", "toward-door"] and p["toward-door"].source == ""
    dd = tmp_path / "dd"
    assert plate_path(dd, "izakaya", p["toward-shelves"]) == dd / "izakaya" / "play.png"
    assert plate_path(dd, "izakaya", p["toward-door"]) == dd / "izakaya" / "plates" / "toward-door.png"
    assert plate_id("izakaya", "toward-door") == "plate--izakaya--toward-door"
    assert load_plates("nowhere", tmp_path) == {}
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement**

```python
# tools/shorts/plates.py
"""Location plates: the empty room from each camera direction a short needs. A plate is approved once (review id
plate--<place>--<name>) and reused by every later short at that place."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

DESIGNS_ROOT = Path("narrator/worlds/designs")


@dataclass
class Plate:
    name: str
    view: str
    source: str = ""   # an existing approved image of the place adopted as this plate


def load_plates(place: str, designs_root: Path = DESIGNS_ROOT) -> dict[str, Plate]:
    path = designs_root / f"{place}.plates.toml"
    if not path.exists():
        return {}
    return {p["name"]: Plate(**p) for p in tomllib.loads(path.read_text()).get("plate", [])}


def plate_path(design_dir: Path, place: str, plate: Plate) -> Path:
    return design_dir / place / (plate.source or f"plates/{plate.name}.png")


def plate_id(place: str, name: str) -> str:
    return f"plate--{place}--{name}"
```

`narrator/worlds/designs/mama-satos-izakaya.plates.toml`:

```toml
# Empty-room plates of Mama Sato's izakaya, one per camera direction. Night, no people.
[[plate]]
name = "toward-shelves"
view = "from the guest stools toward the long wooden counter, bottle shelves, paper lanterns and the red neon sign on the back wall"
source = "play.png"

[[plate]]
name = "toward-door"
view = "from behind the counter toward the guest stools and the noren doorway in the left wall; no windows"

[[plate]]
name = "along-counter"
view = "from the far end of the counter looking along it: stools on the left, counter and shelves on the right, the noren doorway at the back"
```

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `git add tools/shorts/plates.py narrator/worlds/designs/mama-satos-izakaya.plates.toml tests/test_shorts_plates.py && git commit -m "shorts: plate catalogue"`

### Task 8: Prompts use the bible and the plate

**Files:**
- Modify: `tools/shorts/prompt.py`, `tools/shorts/__main__.py` (`_preflight`)
- Test: `tests/test_shorts_prompt.py` (append)

**Interfaces:**
- Consumes: `scene_text` (Task 6), `load_plates`/`plate_path` (Task 7).
- Produces: `build_prompt(short, shot, designs, has_still=False, sent=None)` — unchanged signature; for `shot.mode == "i2v"` returns `i2v_prompt(short, shot, designs)`. `i2v_prompt(short, shot, designs) -> str` built from: motion; `scene_text`; `Wardrobe: C1 Saeko: …; C2 Rin: …`; `Seating: <blocking values>`; screen positions + `line_rule`; locked-off sentence for static; `short.style`; L5 timed rows (lines, acting, beats). `expected_refs(short, design_dir, shot_dir, plate: Path | None = None)` uses `plate` instead of `play.png` when given. In reference mode, `L1` gets `scene_text`, wardrobe and seating appended.

- [ ] **Step 1: Tests**

```python
SCENE_SHORT = SHORT + '''
[scene]
time = "late night"
weather = "indoors; no windows"
set = "a narrow izakaya"
light = ["paper lanterns"]
not_visible = ["rain", "street"]

[wardrobe]
C1 = "navy jacket zipped"

[blocking]
seating = "side by side, C2 on C1's left"
'''


def test_i2v_prompt_has_motion_bible_wardrobe_seating_and_no_ref_header(tmp_path):
    shot = PLANNED + '\nmotion = "C2 turns to C1."\n'
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=shot))
    p = build_prompt(s, s.shots[0], designs())
    assert p.startswith("C2 turns to C1.")
    assert "Not visible: rain, street." in p and "Wardrobe: C1 " in p and "navy jacket zipped" in p
    assert "Seating: side by side, C2 on C1's left." in p and "@Image" not in p and "grey-box" not in p


def test_reference_mode_keeps_roles_and_adds_bible(tmp_path):
    shot = PLANNED + '\nmode = "reference"\n'
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=shot))
    p = build_prompt(s, s.shots[0], designs(), sent=["C1_turnaround.png", "place.png", "greybox.mp4"])
    assert "@Image2 is the location" in p and "Time: late night." in p and "Seating:" in p


def test_expected_refs_uses_the_shot_plate(tmp_path):
    from tools.shorts.prompt import expected_refs
    s = load_short(write(tmp_path, shot=PLANNED))
    plate = tmp_path / "plate.png"
    refs = dict(expected_refs(s, tmp_path / "dd", tmp_path / "sd", plate=plate))
    assert refs["place.png"] == plate
```

The existing prompt tests use shots without `mode`, which now default to `i2v`. Update `PLANNED`-based existing tests that assert reference-mode layers (`layers(...)`, `@Image` header, `Floor plan`) by adding `mode = "reference"` to the shot text they load, so they keep testing the reference path.

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** in `prompt.py`:

```python
from tools.shorts.model import scene_text


def _package_lines(short: Short, designs: dict) -> list[str]:
    out = [scene_text(short)] if short.scene else []
    if short.wardrobe:
        out.append("Wardrobe: " + "; ".join(f"{cid} {designs[short.cast[cid]].name}: {w}" for cid, w in short.wardrobe.items()) + ".")
    if short.blocking:
        out.append("Seating: " + "; ".join(short.blocking.values()) + ".")
    return [x for x in out if x]


def _positions(short: Short, shot: Shot) -> str:
    parts = [f"{c} {w}" for c, w in shot.frame.items()] + ([short.line_rule] if short.line_rule else [])
    return ("Screen positions: " + "; ".join(parts) + ".") if parts else ""


def i2v_prompt(short: Short, shot: Shot, designs: dict) -> str:
    """Image-to-video: the start (and end) keyframe already shows the room, people and outfits; the text says what
    moves, restates what must not change, and lists what must not appear."""
    head = [shot.motion or shot.action, *_package_lines(short, designs), _positions(short, shot)]
    if shot.move == "static":
        head.append("Keep the camera completely locked off.")
    l5 = layers(short, shot, designs)["L5"]
    return "\n\n".join([" ".join(x for x in head if x), short.style, l5])
```

In `build_prompt`, first line: `if shot.mode == "i2v": return i2v_prompt(short, shot, designs)`. In `layers`, after the static-camera sentence: `l1 += "".join(" " + x for x in _package_lines(short, designs))` (only reached in reference mode, since i2v returns early; `i2v_prompt` itself calls `layers` only for `L5`, so guard: move the `_package_lines` append under `if shot.mode == "reference":`). Remove the `l1 += " Screen positions: …"` block in `layers` and use `_positions` instead (same text). `expected_refs(..., plate=None)`: `out.append(("start_frame.png", still) if still.exists() else ("place.png", plate or design_dir / short.place / "play.png"))`.

In `__main__._preflight`: resolve the plate:

```python
    from tools.shorts.plates import load_plates, plate_path
    plates = load_plates(s.place)
    plate = plate_path(data_dir().parent, s.place, plates[shot.plate]) if shot.plate in plates else None
    expected = expected_refs(s, data_dir().parent, shot_dir, plate=plate)
```

- [ ] **Step 4: Run** → PASS; full suite.
- [ ] **Step 5: Commit** — `git commit -am "shorts: i2v prompt with scene bible, wardrobe, seating; reference mode uses the shot plate"`

### Task 9: Pre-flight package checks, fingerprint and scene approval

**Files:**
- Modify: `tools/shorts/preflight.py`, `tools/shorts/approve.py`, `tools/shorts/__main__.py`
- Test: `tests/test_shorts_preflight.py`, `tests/test_shorts_approve.py` (append)

**Interfaces:**
- Consumes: Tasks 6-8.
- Produces:
  - `preflight.package(short, shot, prev, plates: dict, shot_dir: Path, approvals: dict) -> list[str]` problems; `preflight.bible_words(short, shot) -> tuple[list[str], list[str]]` (problems, warnings).
  - `preflight.run(short, shot, prev, prompt, ref_list, model, spent, package_problems=(), bible=((), ()))` appends them.
  - `approve.fingerprint(model, prompt, refs, seconds, extra: str = "")` — `extra` is hashed in (mode + scene text); keyframes are included by passing them in `refs` (labels `keyframe-start.png`, `keyframe-end.png`).
  - `approve.scene_fp(short) -> str` (10 hex of SHA-256 over `scene_text` + wardrobe + blocking, sorted); scene approval lives in `approvals.json` under key `"SCENE"` via id `plan--<slug>--scene--<fp>` (existing `apply_approvals` already maps `scene` → `SCENE`).
  - Keyframe paths: `shot_dir / "keyframe-start.png"`, `shot_dir / "keyframe-end.png"`.

Rules (`package`):
1. `shot.plate` empty → `"no plate"`; not in `plates` → `"plate <name> is not in <place>.plates.toml"`; plate file missing → `"plate <name> not rendered"`; plate not approved (no `keep` verdict for `plate_id` in the images API dict passed as `approvals["images"]`) → `"plate <name> not approved"`.
2. `short.scene is None` → `"no [scene] bible"`; scene not approved for current `scene_fp` (`approvals["SCENE"].get(fp)` keep) → `"scene bible not approved (or changed since)"`.
3. i2v: `keyframe-start.png` missing → `"no approved start keyframe"`; `end_frame` true or `set(shot.at_start) != set(shot.at_end)` (someone enters/leaves) and `keyframe-end.png` missing → `"needs an end keyframe"`; `shot.motion` empty → `"missing motion"`.
4. Wardrobe/blocking: if `prev` exists, nothing per shot to compare beyond declarations — the check is that `shot.wardrobe_change`/`blocking_change` are only used when `[at_start]`/`[at_end]` text names the change (skip; YAGNI). Keep only: any cast id in `shot.frame` without a `short.wardrobe` entry → `"<cid> has no [wardrobe] line"`.

`bible_words`: words = `short.scene.not_visible` + weather words `("rain", "raining", "wet street", "snow", "fog", "daylight", "sunlight", "window")` minus any that appear in `short.scene.weather` without a "no " before them. Search (case-insensitive, whole word) `short.style`, every beat text, acting fields, `shot.motion`, `shot.summary`, `shot.action` → problem `"'<word>' in <where> contradicts the scene bible"`; search line texts → warning.

- [ ] **Step 1: Tests** (append to `tests/test_shorts_preflight.py`; use `SCENE_SHORT` text from Task 8 copied into this file as a module constant):

```python
def test_package_problems(tmp_path):
    from tools.shorts.plates import Plate
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=PLANNED + '\nplate = "door"\nend_frame = true\n'))
    sd = tmp_path / "sd"; sd.mkdir()
    p = preflight.package(s, s.shots[0], None, {"door": Plate("door", "v")}, sd,
                          {"images": {}, "SCENE": {}}, tmp_path / "dd")
    for want in ("plate door not rendered", "scene bible not approved", "no approved start keyframe",
                 "needs an end keyframe", "missing motion", "C2 has no [wardrobe] line"):
        assert any(want in x for x in p), (want, p)


def test_bible_words(tmp_path):
    shot = PLANNED.replace('action = "C2 asks who paid her tab."', 'action = "C2 shakes rain off her hood."')
    shot = shot.replace('text = "Who paid it?"', 'text = "Still raining?"')
    s = load_short(write(tmp_path, short=SCENE_SHORT, shot=shot))
    problems, warnings = preflight.bible_words(s, s.shots[0])
    assert any("'rain' in action" in x for x in problems) and any("'raining'" in w for w in warnings)
```

Append to `tests/test_shorts_approve.py`:

```python
def test_fingerprint_extra_and_scene_fp(tmp_path):
    from tools.shorts.approve import fingerprint, scene_fp
    assert fingerprint("m", "p", [], 5, "a") != fingerprint("m", "p", [], 5, "b")
    s1 = load_short(write(tmp_path / "a", short=SCENE_SHORT))
    s2 = load_short(write(tmp_path / "b", short=SCENE_SHORT.replace("late night", "midnight")))
    assert scene_fp(s1) != scene_fp(s2) and len(scene_fp(s1)) == 10
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement**

```python
# preflight.py additions
import hashlib
import re

from tools.shorts.approve import scene_fp
from tools.shorts.plates import plate_id, plate_path

WEATHER = ("rain", "raining", "wet street", "snow", "fog", "daylight", "sunlight", "window")


def package(short, shot, prev, plates: dict, shot_dir, approvals: dict, design_dir) -> list[str]:
    p = []
    if not shot.plate:
        p.append("no plate")
    elif shot.plate not in plates:
        p.append(f"plate {shot.plate} is not in {short.place}.plates.toml")
    elif not plate_path(design_dir, short.place, plates[shot.plate]).exists():
        p.append(f"plate {shot.plate} not rendered")
    elif approvals.get("images", {}).get(plate_id(short.place, shot.plate), {}).get("verdict") != "keep":
        p.append(f"plate {shot.plate} not approved")
    if short.scene is None:
        p.append("no [scene] bible")
    elif approvals.get("SCENE", {}).get(scene_fp(short), {}).get("verdict") != "keep":
        p.append("scene bible not approved (or changed since)")
    if shot.mode == "i2v":
        if not (shot_dir / "keyframe-start.png").exists():
            p.append("no approved start keyframe")
        if (shot.end_frame or set(shot.at_start) != set(shot.at_end)) and not (shot_dir / "keyframe-end.png").exists():
            p.append("needs an end keyframe (end_frame, or someone enters or leaves)")
        if not shot.motion:
            p.append("missing motion")
    p += [f"{cid} has no [wardrobe] line" for cid in shot.frame if cid not in short.wardrobe]
    return p


def _banned(short) -> list[str]:
    if short.scene is None:
        return []
    allowed = short.scene.weather.lower()
    extra = [w for w in WEATHER if w not in allowed or f"no {w}" in allowed]
    return list(dict.fromkeys([w.lower() for w in short.scene.not_visible] + extra))


def bible_words(short, shot) -> tuple[list[str], list[str]]:
    words = _banned(short)
    texts = [("style", short.style), ("summary", shot.summary), ("action", shot.action), ("motion", shot.motion)]
    texts += [("beat", b.text) for b in shot.beats]
    texts += [(f"{a.who} acting", " ".join([a.goal, a.emotion, a.face, a.gaze, a.voice, a.end])) for a in shot.acting]
    problems, warnings = [], []
    for w in words:
        rx = re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE)
        problems += [f"'{w}' in {where} contradicts the scene bible" for where, t in texts if rx.search(t)]
        warnings += [f"'{w}' in a line of dialogue (fine if spoken, not shown)" for ln in shot.lines if rx.search(ln.text)]
    return problems, warnings
```

Change `run(...)` to take `package_problems=(), bible=((), ())` and include `list(package_problems) + list(bible[0])` in problems and `list(bible[1])` in warnings.

```python
# approve.py additions / changes
def fingerprint(model, prompt, refs, seconds, extra: str = "") -> str:
    h = hashlib.sha256(model.encode() + b"\0" + prompt.encode() + b"\0" + str(seconds).encode() + b"\0" + extra.encode())
    for label, path in refs:
        h.update(b"\0" + label.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:10]


def scene_fp(short) -> str:
    from tools.shorts.model import scene_text
    blob = json.dumps([scene_text(short), sorted(short.wardrobe.items()), sorted(short.blocking.items())])
    return hashlib.sha256(blob.encode()).hexdigest()[:10]
```

(`fingerprint` with `extra=""` still differs from the old hash because of the added separator; existing approvals become stale — intended, the shots must be re-approved under the new package anyway.)

In `__main__`: `_preflight` builds `approvals = {**json.loads((work / "approvals.json").read_text()) if exists else {}, "images": _images_api()}` where `_images_api()` GETs `http://192.168.10.19:8080/designs/api/images` (timeout 10 s; on error returns `{}` and the plate check then reports "not approved", which is the safe side). For i2v, `refs` = `[("keyframe-start.png", p), ("keyframe-end.png", p2)]` (existing files only), not the sheets. Pass `extra=f"{shot.mode}\n{scene_text(s)}"` to every `approve.fingerprint` call (submit and `sheet.collect`). `run(...)` gets `package_problems=preflight.package(...)`, `bible=preflight.bible_words(s, shot)`.

- [ ] **Step 4: Run** → PASS; full suite (fix fixtures that now need `mode = "reference"` or a scene, as in Task 8).
- [ ] **Step 5: Commit** — `git commit -am "shorts: package pre-flight checks, scene approval, fingerprint covers mode and bible"`

### Task 10: fal image-to-video, blocked jobs, ledger sync

**Files:**
- Modify: `tools/shorts/backends/fal.py`, `tools/shorts/takes.py`, `tools/shorts/__main__.py`
- Test: `tests/test_shorts_fal.py` (append; the existing fal tests file — find with `grep -l "build_input" tests/`)

**Interfaces:**
- Produces: models `"seedance-2.0-fast-i2v"` and `"seedance-2.0-i2v"` in `MODELS` and `RATES` (0.2419 and 0.3024 $/s at 720p); `build_input` for i2v models sends `image_url` (label `keyframe-start.png`), optional `end_image_url` (`keyframe-end.png`), `aspect_ratio: "auto"`, `resolution: "720p"`; any other ref → `ValueError`. `class Blocked(RuntimeError)`; `fetch` raises `Blocked` when the result GET returns 422. `Ledger.add(..., status="")` stores `status` when set; `Ledger.total()` counts `cost` of every row (blocked rows stay counted until synced). `Ledger.adjust(balance_left: float, budget: float, note: str)` appends `{"shot": "-", "take": "adjust", "model": "-", "cost": round((budget - balance_left) - total, 4), "note": note, "status": "adjust"}` so `budget - total == balance_left`. CLI `ledger-sync <slug> --balance X` calls it with `s.budget_usd`.
- `run_take`: on `Blocked`, rewrite the just-added ledger row's `status` to `"blocked"` and re-raise as `RuntimeError("blocked by fal content moderation (partner_validation_failed); refs: …; the charge may or may not apply — run ledger-sync with the balance from fal's billing page")`.

- [ ] **Step 1: Tests**

```python
def test_i2v_body_start_end_and_rejects_sheets(tmp_path, monkeypatch):
    from tools.shorts.backends import fal
    monkeypatch.setattr(fal, "data_uri", lambda p: f"uri:{p.name}")
    a, b = tmp_path / "keyframe-start.png", tmp_path / "keyframe-end.png"
    body = fal.build_input("seedance-2.0-fast-i2v", "p", [("keyframe-start.png", a), ("keyframe-end.png", b)], 8)
    assert body["image_url"] == "uri:keyframe-start.png" and body["end_image_url"] == "uri:keyframe-end.png"
    assert body["duration"] == "8" and body["aspect_ratio"] == "auto" and "image_urls" not in body
    import pytest
    with pytest.raises(ValueError):
        fal.build_input("seedance-2.0-fast-i2v", "p", [("C1_turnaround.png", a)], 8)


def test_ledger_adjust_matches_real_balance(tmp_path):
    from tools.shorts.takes import Ledger
    led = Ledger(tmp_path / "costs.json")
    led.add("S01", "t1", "m", 23.45)
    led.add("S02", "t2", "m", 1.0, status="blocked")
    led.adjust(3.29, 25.0, "fal billing 2026-11-10")
    assert round(25.0 - led.total(), 2) == 3.29
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** — in `fal.py` `MODELS`:

```python
    "seedance-2.0-fast-i2v": {"endpoint": "bytedance/seedance-2.0/fast/image-to-video", "prompt": "prompt", "i2v": True,
                              "duration": "duration", "duration_str": True, "min_s": 4,
                              "extra": {"resolution": "720p", "aspect_ratio": "auto"}},
    "seedance-2.0-i2v": {"endpoint": "bytedance/seedance-2.0/image-to-video", "prompt": "prompt", "i2v": True,
                         "duration": "duration", "duration_str": True, "min_s": 4,
                         "extra": {"resolution": "720p", "aspect_ratio": "auto"}},
```

At the top of `build_input`:

```python
    if spec.get("i2v"):
        refs = dict(refs)
        bad = [l for l in refs if l not in ("keyframe-start.png", "keyframe-end.png")]
        if bad or "keyframe-start.png" not in refs:
            raise ValueError(f"{model} takes keyframe-start.png and optional keyframe-end.png only, got {list(refs)}")
        body = {spec["prompt"]: prompt, spec["duration"]: str(secs), **spec["extra"],
                "image_url": data_uri(refs["keyframe-start.png"])}
        if "keyframe-end.png" in refs:
            body["end_image_url"] = data_uri(refs["keyframe-end.png"])
        return body
```

(`secs` computed before this block.) `usable_refs`: for i2v models return refs whose label starts with `keyframe-`, others in `out`; `max_images` absent → preflight's image-limit check must use `spec.get("max_images", 2)`. In `fetch`, replace the result GET with:

```python
    r = client.get(job["response_url"], headers=headers, timeout=60)
    if r.status_code == 422:
        raise Blocked(r.text[:300])
    result = r.raise_for_status().json()
```

`takes.py`: `RATES["seedance-2.0-fast-i2v"] = 0.2419`, `RATES["seedance-2.0-i2v"] = 0.3024`; `Ledger.add(..., status: str = "")` adds `row["status"] = status` when set; `Ledger.set_status(take, status)` rewrites the matching row; `Ledger.adjust` as above. `__main__`: `ledger-sync` subcommand (`slug`, `--balance` float required) printing old and new remaining. Update the submit error message for `Blocked`.

- [ ] **Step 4: Run** → PASS; full suite.
- [ ] **Step 5: Commit** — `git commit -am "shorts: Seedance 2.0 image-to-video, moderation blocks recorded, ledger-sync"`

## Phase C — Renders, page, pilot

### Task 11: Grey-box guides (room-only frames, lineart, regions)

**Files:**
- Modify: `tools/shorts/greybox/blender_build.py`
- Create: `tools/shorts/guides.py`
- Test: `tests/test_shorts_guides.py`

**Interfaces:**
- Produces (Blender, per shot, under `shots/<id>/guide/`): `start.png`, `end.png` (current preview frames re-rendered at the keyframe size 1216×832 with flat white objects on black: `sc.display.shading.light = "FLAT"`, objects colour white, world black); `start-room.png`, `end-room.png` (same with figures hidden: `obj.hide_render = True` for figure objects); `regions.json` = `{"start": {"C1": [x0, y0, x1, y1], ...}, "end": {...}}` in 0..1 image fractions from projecting each figure's bounding-box corners with `bpy_extras.object_utils.world_to_camera_view` (y flipped: `1 - co.y`), clamped to 0..1, omitted when fully off screen.
- `guides.lineart(src: Path, out: Path) -> Path` — white edges on black: `ImageOps.grayscale` → `ImageFilter.FIND_EDGES` → threshold 40 → `MaxFilter(3)`; `guides.regions(shot_dir) -> dict` loads regions.json.
- Keyframe size constant `KEY_W, KEY_H = 1216, 832` in `guides.py` (16:11, close to the house SCENE_SIZE; the i2v aspect is taken from the image).

- [ ] **Step 1: Test** (pure Python part only; Blender is verified on the box in Step 4)

```python
# tests/test_shorts_guides.py
from PIL import Image, ImageDraw

from tools.shorts.guides import lineart


def test_lineart_draws_edges_white_on_black(tmp_path):
    src = tmp_path / "g.png"
    im = Image.new("RGB", (100, 100), "black")
    ImageDraw.Draw(im).rectangle([30, 30, 70, 70], fill="white")
    im.save(src)
    out = Image.open(lineart(src, tmp_path / "l.png")).convert("L")
    assert out.getpixel((50, 50)) == 0 and out.getpixel((5, 5)) == 0
    assert max(out.getpixel((30, y)) for y in range(30, 71)) == 255
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `guides.py`:

```python
"""Turn the grey-box guide renders into what keyframe workflows need: a lineart control image and screen regions."""

import json
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

KEY_W, KEY_H = 1216, 832


def lineart(src: Path, out: Path) -> Path:
    g = ImageOps.grayscale(Image.open(src)).filter(ImageFilter.FIND_EDGES)
    g = g.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(3))
    out.parent.mkdir(parents=True, exist_ok=True)
    g.convert("RGB").save(out)
    return out


def regions(shot_dir: Path) -> dict:
    path = shot_dir / "guide" / "regions.json"
    return json.loads(path.read_text()) if path.exists() else {}
```

In `blender_build.py`, after each shot's preview loop add a guide block: set resolution to 1216×832 for the guide renders only (restore after), switch to flat white-on-black, render `start`/`end` (frames `start` and `last`), hide figures and render `-room` variants, unhide, and write `regions.json` using:

```python
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

def screen_box(obj, cam):
    pts = [world_to_camera_view(sc, cam, obj.matrix_world @ Vector(c)) for c in obj.bound_box]
    for child in obj.children_recursive:
        pts += [world_to_camera_view(sc, cam, child.matrix_world @ Vector(c)) for c in child.bound_box]
    xs = [min(max(p.x, 0), 1) for p in pts if p.z > 0]
    ys = [min(max(1 - p.y, 0), 1) for p in pts if p.z > 0]
    if not xs or max(xs) - min(xs) < 0.01:
        return None
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]
```

(`figures` dict already maps id → object; mannequin parts must be children of that object — check `mannequin()`; if parts are separate objects, collect them by name prefix `f"{fid}_"`.)

Add CLI `python -m tools.shorts guides <slug>`: runs the existing grey-box Blender step on the GPU box the same way `greybox` does (reuse its remote call), then for each shot writes `guide/start-lineart.png`, `guide/end-lineart.png`, `guide/start-room-lineart.png`, `guide/end-room-lineart.png` with `lineart`.

- [ ] **Step 4: Verify on the box** — run `guides saeko-rin-izakaya`; open `S01/guide/start.png`, `end.png`, `start-lineart.png` and check `regions.json` has C1 in `start` and C1+C2 in `end` for S01; C2 (and C1 partly) in S02 start. View the lineart images at full size.
- [ ] **Step 5: Commit** — `git commit -am "shorts: grey-box guide renders, lineart and screen regions"`

### Task 12: Plates render + plate and scene review items

**Files:**
- Modify: `tools/shorts/plates.py`, `tools/shorts/__main__.py`, `tools/review/producers.py`
- Test: `tests/test_shorts_plates.py`, `tests/test_review_producers.py` (append)

**Interfaces:**
- Consumes: `imagegen.build`, guides (Task 11), `scene_text`, `scene_fp`, `plate_id`.
- Produces: `plates.plate_workflow(place_design, scene_text: str, plate: Plate, lineart_name: str | None, seed: int) -> dict`; CLI `plates <slug> [--seeds 3]` renders, for each plate named by a shot and missing on disk, `--seeds` candidates to `design-data/<place>/plates/<name>-cNN.png` using the lineart of the first shot that names the plate (`guide/start-room-lineart.png`, uploaded to ComfyUI input like `design_sheets` does for the pose image); `plates <slug> --choose <name> <n>` copies `<name>-c<n>.png` to `<name>.png`. Producers: `plates(ctx)` (one Item per plate candidate set: id `plate--<place>--<name>`, kind `plate`, stage `pre-production`, files = the chosen `<name>.png` if present else candidates; compare = the place's `play.png` labelled "Approved room"; context = plate.view) and `scenes(ctx)` (per short with a `[scene]`: id `plan--<slug>--scene--<scene_fp>`, kind `scene`, files = the place's `play.png`, context = scene_text + wardrobe + blocking). Append both to `ALL`.

`plate_workflow`:

```python
def plate_workflow(place, scene: str, plate, lineart_name, seed: int) -> dict:
    from tools.imagegen import build
    tags = place.alt_tags or place.tags
    wf = build(f"{tags}, {plate.view}, empty room, no humans, {scene}", "scene", False,
               "people, person, 1girl, 1boy, window, street, rain, daylight", "base", seed)
    wf["5"]["inputs"].update(width=1216, height=832)
    if lineart_name:
        wf["60"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "noob-sdxl-controlnet-lineart_anime.fp16.safetensors"}}
        wf["61"] = {"class_type": "LoadImage", "inputs": {"image": lineart_name}}
        wf["62"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": wf["3"]["inputs"]["positive"],
                    "negative": wf["3"]["inputs"]["negative"], "control_net": ["60", 0], "image": ["61", 0],
                    "strength": 0.55, "start_percent": 0.0, "end_percent": 0.6}}
        wf["3"]["inputs"].update(positive=["62", 0], negative=["62", 1])
    wf["9"]["inputs"]["filename_prefix"] = f"nightwire_plates/{plate.name}"
    return wf
```

Note: `build(... "base" ...)` may route through `sheet_workflow` (high-res, second KSampler "34") — if `wf` has node `"34"`, apply the same ControlNet to `"34"` positive/negative too. Check `SIZES["base"]` in imagegen and handle both.

- [ ] **Step 1: Tests** — `plate_workflow` adds nodes 60-62 and rewires sampler "3" when lineart is given, sets 1216×832, prompt contains `plate.view` and "no humans"; producers return the plate and scene items with the ids above (use a fake design namespace and tmp files).
- [ ] **Step 2-4:** fail → implement → pass; full suite.
- [ ] **Step 5: Commit** — `git commit -am "shorts: plate renders; plate and scene items in the review inbox"`

### Task 13: Keyframes

**Files:**
- Create: `tools/shorts/keyframes.py`
- Modify: `tools/shorts/__main__.py`, `tools/review/producers.py`
- Test: `tests/test_shorts_keyframes.py`

**Interfaces:**
- Consumes: guides (Task 11), plates (Task 7/12), `design_scenes._region_tags`, `image_studio._subject`, `imagegen.build`, `stills.SIZE_WORDS`.
- Produces: `keyframe_workflow(short, shot, designs, which: str, regions: dict, lineart_name: str, seed: int) -> dict`; CLI `keyframes <slug> [shot] [--which start|end|both] [--seeds 4]` renders candidates `shots/<id>/keyframes/<which>-cNN.png` (one GPU job at a time, VRAM freed after, taste check first); `keyframes <slug> <shot> --choose start 3` copies the candidate to `shots/<id>/keyframe-start.png`. Producer `keyframes(ctx)`: per short shot and `which`, one Item id `key--<slug>--<shot lower>--<which>` kind `keyframe`, stage `pre-production`, files = chosen file if present else candidates (max 6), compare = each in-frame character's `turnaround.png` (shorts copy when present) and `portrait.png` + the shot's plate file + `guide/<which>.png` labelled "Grey-box"; context = the shot's `[frame]`, `[at_start]`/`[at_end]`, props, wardrobe lines. A `keep` on the chosen file means approved; Claude chooses among candidates first (house rule: full-size review beside the turnaround), so the owner normally sees 1-3.

Workflow (per character region from `regions[which]`):

```python
def keyframe_workflow(short, shot, designs, which, regions, lineart_name, seed):
    from tools.design_scenes import _region_tags
    from tools.image_studio import _subject
    from tools.imagegen import build
    from tools.shorts.model import scene_text
    from tools.shorts.stills import SIZE_WORDS
    place = designs[short.place]
    boxes = regions.get(which, {})
    who = [c for c in boxes if c in short.cast]
    count = {1: "solo", 2: "2girls"}.get(len(who), "")
    words = ", ".join(x for x in (count, SIZE_WORDS.get(shot.size, ""), shot.angle, place.alt_tags or place.tags,
                                   scene_text(short)) if x)
    negative = "window, street, rain, daylight, merged bodies, fused faces, extra arms, open jacket, cleavage"
    wf = build(words, "scene" if not who else "subject", False, negative, "base", seed)
    wf["5"]["inputs"].update(width=1216, height=832)
    clip, combined = wf["6"]["inputs"]["clip"], ["6", 0]
    for i, cid in enumerate(who):
        d = designs[short.cast[cid]]
        x0, y0, x1, y1 = boxes[cid]
        text = ", ".join(x for x in (_subject(d), _region_tags(d), short.locks.get(cid, ""), short.wardrobe.get(cid, ""),
                                      shot.props.get(cid, "")) if x)
        n = 70 + i * 3
        wf[str(n)] = {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": clip}}
        wf[str(n + 1)] = {"class_type": "ConditioningSetArea", "inputs": {"conditioning": [str(n), 0],
                          "width": max(64, int((x1 - x0) * 1216) // 8 * 8), "height": max(64, int((y1 - y0) * 832) // 8 * 8),
                          "x": int(x0 * 1216) // 8 * 8, "y": int(y0 * 832) // 8 * 8, "strength": 1.2}}
        wf[str(n + 2)] = {"class_type": "ConditioningCombine", "inputs": {"conditioning_1": combined, "conditioning_2": [str(n + 1), 0]}}
        combined = [str(n + 2), 0]
    wf["60"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "noob-sdxl-controlnet-lineart_anime.fp16.safetensors"}}
    wf["61"] = {"class_type": "LoadImage", "inputs": {"image": lineart_name}}
    wf["62"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": combined, "negative": wf["3"]["inputs"]["negative"],
                "control_net": ["60", 0], "image": ["61", 0], "strength": 0.6, "start_percent": 0.0, "end_percent": 0.65}}
    wf["3"]["inputs"].update(positive=["62", 0], negative=["62", 1])
    wf["9"]["inputs"]["filename_prefix"] = f"nightwire_shorts/{short.slug}-{shot.id}-{which}"
    return wf
```

(As in Task 12: if the built workflow has a high-res second sampler `"34"`, give it the same positive/negative.) Two characters of different subject (1boy/1girl) use `design_scenes._crowd` for `count`.

- [ ] **Step 1: Tests** — with fake designs (SimpleNamespace with `required`, `tags`, `held`, `negative`, `alt_tags`) and regions `{"start": {"C1": [0.5, 0.1, 0.9, 1.0], "C2": [0.1, 0.1, 0.45, 1.0]}}`: the workflow has two ConditioningSetArea nodes with x/width matching the boxes (multiples of 8), the ControlNet nodes 60-62 wired into sampler "3", wardrobe and lock text in each region prompt, and "rain" in the negative; with `regions={}` no area nodes and kind "scene". Producer test: candidates → files list; chosen file present → files == [chosen] and compare includes "Grey-box".
- [ ] **Step 2-4:** fail → implement → pass; full suite.
- [ ] **Step 5: Commit** — `git commit -am "shorts: keyframe candidates from grey-box lineart and screen regions; keyframes in the inbox"`

Fix passes: after choosing, Claude runs `python -m tools.fix_area` on faces/hands/outfit (existing tool; refuses changes outside the mask, writes a compare) until the keyframe matches the turnaround at full size; the fixed file replaces `keyframe-<which>.png` and the owner reviews the result in the inbox. Fallback B (fal image model) only with the owner's OK, logged as a ledger row with `note = "keyframe fallback"`.

### Task 14: Per-short page with stage tabs

**Files:**
- Modify: `tools/shorts/sheet.py`, `tools/shorts/sheet.html`, `tools/shorts/__main__.py` (`cmd_sheet` writes to `_site/<slug>/index.html`; keep `_site/<slug>/sheet/index.html` as a redirect `<meta http-equiv="refresh" content="0; url=../">`)
- Test: `tests/test_shorts_sheet.py` (append)

**Interfaces:**
- Consumes: `preflight.package`, `scene_fp`, `load_plates`, keyframe paths.
- Produces: `sheet.stages(short, plans, plates, approvals, work) -> list[dict]` — six entries in order `Bible, Plates, Keyframes, Shots, Takes, Cut`, each `{"name", "status": "locked"|"waiting"|"approved", "detail"}`: Bible approved when the scene approval for `scene_fp` is keep; Plates approved when every named plate is approved; Keyframes approved when every i2v shot has its keyframes and each has a keep for `key--…`; Shots approved when every shot's plan fp is keep; Takes approved when every shot has a kept take; Cut approved when `cut.mp4`/`draft.mp4` exists and has a keep. A stage is `locked` while any earlier stage is not approved; otherwise `waiting` or `approved`. `collect()` adds `"stages"` to its data. `sheet.html` renders the tabs at the top (status chip per tab), the existing sections under Shots, the bible (scene text, wardrobe, seating) under Bible, plate thumbnails under Plates, keyframes per shot under Keyframes, and a link "Review these in the inbox" → `/review/?project=<slug>` in every tab. The page's own Approve/Change/Reject buttons are removed (decisions happen in the inbox); the page is read-only status.

- [ ] **Step 1: Test** — `stages()` with: no scene approval → Bible waiting, all later locked; Bible+Plates approved, keyframes missing → Keyframes waiting, Shots locked.
- [ ] **Step 2-4:** fail → implement → pass; full suite.
- [ ] **Step 5:** Add a producer `plans(ctx)` (if not already from Task 12) that turns each shot's plan (`sheet.collect` output: `image_id`, `prompt`, `refs`, `cost`, problems) into an Item kind `plan`, stage `pre-production`, files = the shot's `keyframe-start.png` web copy (or grey-box `preview/start.png`), context = cost + problems + prompt; skip shots whose pre-flight has problems other than "not approved" ones (they are not ready to approve). Commit — `git commit -am "shorts: per-short page with stage gates; shot plans in the inbox"`

### Task 15: Pilot filled in, published, verified (operational)

**Files:**
- Modify: `narrator/worlds/shorts/saeko-rin-izakaya/short.toml`, `shots/S01.toml`, `S02.toml`, `S03.toml`

- [ ] **Step 1:** In `short.toml`: set `style` to the look only — `"anime screenshot coloring, cel shading, thick outlines, night, warm paper-lantern light with pink rim light and cyan backlight, high contrast, bloom, steam, mature gritty cyberpunk"`; change `beats[1]` text "C2 walks straight to her" unchanged; add:

```toml
[scene]
time = "late night, about 01:00"
weather = "indoors; no windows; no rain and no street visible"
set = "Mama Sato's izakaya: one long wooden counter with guest stools on one side, bottle shelves and paper lanterns behind it, the noren doorway in the left wall"
light = ["amber paper lanterns over the counter", "red neon sign on the back wall", "yellow strip light under the top shelf", "faint cool backlight from the kitchen pass"]
not_visible = ["windows", "street", "rain", "daylight", "other customers"]

[wardrobe]
C1 = "cropped navy jacket with red trim zipped shut to the high collar, black trousers, chrome right hand with an amber ring light on the wrist"
C2 = "white hoodie, white-silver cyberdeck on a strap across her chest"

[blocking]
seating = "C1 sits on a guest stool facing the counter; C2 ends on the stool to C1's left, turned toward her"
```

Shots: S01 `plate = "along-counter"`, `motion = "Slow push in. C2 parts the noren in the background, walks along the stools behind C1 and stops one stool to her left; C1's human left hand covers the chrome hand."`, `end_frame = true`; S02 `plate = "toward-door"`, `motion = "Static. C2 speaks to C1, then lays the data cable's metal jack on the counter and slides it toward C1's chrome hand."`; S03 `plate = "toward-door"` (reverse over C2's shoulder; adjust if the grey-box camera shows the shelves side — check `S03/guide/start-room.png` and use `toward-shelves` if so), `motion = "Slow push in. The amber wrist light blinks faster; C1 answers, turns the data jack over once and does not connect it."`, `end_frame = true`. Remove "rain-soaked" from S01 `[state]` C2 (→ "damp hood up, cyberdeck strap across her chest, tired and watchful") and "out of the rain"/"shakes the rain off" wording from S01 action/acting (→ "comes in through the noren", "shakes her hood back"). Run `preflight saeko-rin-izakaya` and confirm the only problems are approvals/renders still to come, and no bible-word problems.
- [ ] **Step 2:** `guides`, then `plates --seeds 3` (GPU). Claude reviews every plate candidate at full size (no windows, no rain, matches `play.png` look), chooses one per plate with `--choose`, rebuilds the inbox, publishes. **Owner approves plates and the scene bible in the inbox.**
- [ ] **Step 3:** `keyframes saeko-rin-izakaya --which both --seeds 4` (GPU). Claude reviews candidates beside the turnarounds, chooses, runs `fix_area` passes, publishes. **Owner approves keyframes.**
- [ ] **Step 4:** `ledger-sync saeko-rin-izakaya --balance <owner's current fal balance>` (owner states it; owner may top up first). `sheet`/`review build`/publish; **owner approves each shot plan** in the inbox.
- [ ] **Step 5:** Submit approved shots with `--model seedance-2.0-fast-i2v`, one at a time, owner having approved each. Publish takes; owner judges them in the inbox.
- [ ] **Step 6:** Update memory `nightwire_shorts_studio.md`; full test suite; ask the owner before merging/pushing both repos (CI check first).
