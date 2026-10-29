"""Phase 19b design studio CLI: render, approve and export Kuroshio's
character model sheets and location designs.

    python -m tools.design_studio candidates mama-sato | --all-drafts | --rerolls
    python -m tools.design_studio approve mama-sato 3
    python -m tools.design_studio reroll mama-sato "older, thinner"
    python -m tools.design_studio sheets mama-sato | --approved-missing
    python -m tools.design_studio gallery
    python -m tools.design_studio export

Runbook: when applying picks from a published gallery, pass `--round <r>` to
`approve` (the gallery shows a specific round; the default is the latest).
Don't run two batches at once -- they share the GPU and the design TOMLs.
"""

import argparse
import asyncio
import datetime as dt
import html
import io
import json
import os
import random
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

from narrator.comfyui_backend import ComfyUIBackend
from narrator.design_sheets import (
    CHARACTER_SHEETS, LOCATION_SHEETS, MOOD_SUFFIXES, candidate_prompt, candidate_workflow,
    extract_palette, join_strip, sheet_prompt, sheet_workflow,
)
from narrator.designs import DESIGNS_DIR, Design, load_design, load_designs, save_design

_CANDIDATE = re.compile(r"^r(\d+)-c(\d+)-(\d+)\.png$")
CANDIDATES_PER_ROUND = 4


def _today() -> str:
    return dt.date.today().isoformat()


def next_round(slug_dir: Path) -> int:
    rounds = [int(m.group(1)) for p in (slug_dir / "candidates").glob("*.png") if (m := _CANDIDATE.match(p.name))]
    return max(rounds, default=0) + 1


def _latest_candidates(slug_dir: Path, round_no: int | None = None) -> tuple[int, dict[int, Path]]:
    found: dict[int, dict[int, Path]] = {}
    for p in (slug_dir / "candidates").glob("*.png"):
        if m := _CANDIDATE.match(p.name):
            found.setdefault(int(m.group(1)), {})[int(m.group(2))] = p
    if not found:
        return 0, {}
    r = round_no or max(found)
    return r, found.get(r, {})


def _gpu_etiquette(comfyui_url: str, before: bool) -> None:
    try:
        if before:
            host = os.environ.get("OLLAMA_HOST", "http://192.168.10.19:11434").rstrip("/")
            if "://" not in host:
                host = f"http://{host}"
            try:
                r = urllib.request.urlopen(urllib.request.Request(f"{host}/api/ps"), timeout=10)
                models = [m["name"] for m in json.loads(r.read()).get("models", [])]
            except Exception:
                models = [os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b")]
            for model in models:
                body = {"model": model, "keep_alive": 0}
                urllib.request.urlopen(urllib.request.Request(f"{host}/api/generate", data=json.dumps(body).encode()), timeout=30)
        else:
            body = {"unload_models": True, "free_memory": True}
            urllib.request.urlopen(urllib.request.Request(f"{comfyui_url.rstrip('/')}/free", data=json.dumps(body).encode(),
                                                          headers={"Content-Type": "application/json"}), timeout=30)
    except Exception as e:  # best-effort: never block a render batch
        print(f"gpu etiquette skipped: {e}", file=sys.stderr)


async def cmd_candidates(designs: dict[str, Design], slugs: list[str], args, backend) -> int:
    failed = 0
    for slug in slugs:
        try:
            await _candidates_one(slug, args, backend)
        except Exception as e:
            failed += 1
            print(f"{slug}: FAILED: {e}", file=sys.stderr)
    return 1 if failed else 0


async def _candidates_one(slug: str, args, backend) -> None:
    d = load_design(args.designs_dir / f"{slug}.toml")  # pick up hand edits made mid-batch
    slug_dir = args.design_dir / slug
    (slug_dir / "candidates").mkdir(parents=True, exist_ok=True)
    r = next_round(slug_dir)
    pos, neg = candidate_prompt(d)
    for n in range(1, CANDIDATES_PER_ROUND + 1):
        seed = random.randint(1, 2**32 - 1)
        png = await backend.run_workflow(candidate_workflow(pos, neg, seed))
        (slug_dir / "candidates" / f"r{r}-c{n}-{seed}.png").write_bytes(png)
        print(f"{slug}: round {r} candidate {n} (seed {seed})", flush=True)
    if d.status != "approved":
        d.status = "candidates"
    d.notes.append(f"{_today()} round {r}: {CANDIDATES_PER_ROUND} candidates")
    save_design(d, args.designs_dir / f"{slug}.toml")


def cmd_approve(designs, slug: str, n: int, round_no: int | None, args) -> int:
    d = designs[slug]
    r, cands = _latest_candidates(args.design_dir / slug, round_no)
    if n not in cands:
        print(f"{slug}: no candidate #{n} in round {r}", file=sys.stderr)
        return 1
    d.seed = int(_CANDIDATE.match(cands[n].name).group(3))
    d.status = "approved"
    d.palette = []
    sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
    for sheet in sheets:  # stale sheets were rendered from the old seed
        (args.design_dir / slug / f"{sheet}.png").unlink(missing_ok=True)
    d.notes.append(f"{_today()} approved r{r} #{n} (seed {d.seed})")
    save_design(d, args.designs_dir / f"{slug}.toml")
    return 0


def cmd_reroll(designs, slug: str, note: str, args) -> int:
    d = designs[slug]
    if d.status == "approved":
        d.status = "candidates"
    d.notes.append(f"{_today()} reroll: {note}")
    save_design(d, args.designs_dir / f"{slug}.toml")
    return 0


async def cmd_sheets(designs, slugs: list[str], args, backend) -> int:
    failed = 0
    for slug in slugs:
        try:
            await _sheets_one(slug, args, backend)
        except Exception as e:
            failed += 1
            print(f"{slug}: FAILED: {e}", file=sys.stderr)
    return 1 if failed else 0


async def _sheets_one(slug: str, args, backend) -> None:
    d = load_design(args.designs_dir / f"{slug}.toml")  # pick up hand edits made mid-batch
    if d.status != "approved":
        print(f"{slug}: not approved, skipping", file=sys.stderr)
        return
    slug_dir = args.design_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
    for sheet in sheets:
        if sheet == "moodkeys":
            frames = []
            for mood in MOOD_SUFFIXES:
                pos, neg = sheet_prompt(d, sheet, mood=mood)
                frames.append(await backend.run_workflow(sheet_workflow(pos, neg, d.seed, high_res=False)))
            png = join_strip(frames)
        else:
            pos, neg = sheet_prompt(d, sheet)
            png = await backend.run_workflow(sheet_workflow(pos, neg, d.seed))
        (slug_dir / f"{sheet}.png").write_bytes(png)
        print(f"{slug}: {sheet}", flush=True)
    key = "turnaround" if d.kind == "character" else "establishing"
    d.palette = extract_palette((slug_dir / f"{key}.png").read_bytes())
    save_design(d, args.designs_dir / f"{slug}.toml")


def _sheets_present(d: Design, slug_dir: Path) -> bool:
    sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
    return all((slug_dir / f"{s}.png").exists() for s in sheets)


def _web_copy(src: Path, dest: Path) -> None:
    im = Image.open(src).convert("RGB")
    im.thumbnail((1100, 1100))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=84)


def cmd_gallery(designs, args) -> int:
    out = args.design_dir / "gallery"
    sections = []
    for slug, d in designs.items():
        slug_dir = args.design_dir / slug
        r, cands = _latest_candidates(slug_dir)
        figs = []
        for n, p in sorted(cands.items()):
            rel = f"img/{slug}/r{r}-c{n}.jpg"
            _web_copy(p, out / rel)
            figs.append(f'<figure><img src="{rel}" alt="{html.escape(d.name)} candidate {n}"><figcaption>#{n}</figcaption></figure>')
        sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
        for s in sheets:
            if (slug_dir / f"{s}.png").exists():
                rel = f"img/{slug}/{s}.jpg"
                _web_copy(slug_dir / f"{s}.png", out / rel)
                figs.append(f'<figure><img src="{rel}" alt="{html.escape(d.name)} {s}"><figcaption>{s}</figcaption></figure>')
        notes = "".join(f"<li>{html.escape(n)}</li>" for n in d.notes[-3:])
        sections.append(
            f'<section><h2>{html.escape(d.name)} <small>{d.kind} · {d.status} · round {r}</small></h2>'
            f'<p class="tags">{html.escape(d.tags)}</p><div class="grid">{"".join(figs)}</div><ul>{notes}</ul></section>')
    page = ("<!doctype html><meta charset=utf-8><title>Kuroshio Design Studio</title>"
            "<style>body{background:#0d0b14;color:#e9e4f2;font:15px/1.5 system-ui;padding:24px}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}"
            "img{width:100%;display:block}figure{margin:0;background:#16121f}figcaption{padding:4px 8px;color:#ffe14d}"
            ".tags{color:#9a91ad;font:12px ui-monospace,monospace}h2 small{color:#9a91ad;font-weight:400}</style>"
            + "".join(sections))
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page)
    print(out / "index.html")
    return 0


def cmd_export(designs, args) -> int:
    exports = args.design_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    path = exports / f"nightwire-designs-{_today()}.zip"
    index = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for slug, d in designs.items():
            slug_dir = args.design_dir / slug
            if d.status != "approved" or not _sheets_present(d, slug_dir):
                continue
            z.write(args.designs_dir / f"{slug}.toml", f"{slug}/design.toml")
            sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
            for s in sheets:
                z.write(slug_dir / f"{s}.png", f"{slug}/{s}.png")
            index.append(f'<li><a href="{slug}/">{html.escape(d.name)}</a> ({d.kind})</li>')
        z.writestr("index.html", "<!doctype html><meta charset=utf-8><title>Nightwire designs</title><ul>"
                   + "".join(index) + "</ul>")
    print(path)
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.design_studio")
    p.add_argument("--designs-dir", type=Path, default=DESIGNS_DIR)
    p.add_argument("--design-dir", type=Path, default=Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")))
    p.add_argument("--comfyui-url", default=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"))
    p.add_argument("--no-gpu-etiquette", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("candidates"); c.add_argument("slugs", nargs="*")
    c.add_argument("--all-drafts", action="store_true"); c.add_argument("--rerolls", action="store_true")
    a = sub.add_parser("approve"); a.add_argument("slug"); a.add_argument("n", type=int); a.add_argument("--round", type=int)
    r = sub.add_parser("reroll"); r.add_argument("slug"); r.add_argument("note")
    s = sub.add_parser("sheets"); s.add_argument("slugs", nargs="*"); s.add_argument("--approved-missing", action="store_true")
    sub.add_parser("gallery"); sub.add_parser("export")
    return p


async def main(argv: list[str], backend=None) -> int:
    args = _parser().parse_args(argv)
    designs = load_designs(args.designs_dir)
    for slug in getattr(args, "slugs", []) or ([args.slug] if hasattr(args, "slug") else []):
        if slug not in designs:
            print(f"unknown design {slug!r}", file=sys.stderr)
            return 1
    if args.command in ("candidates", "sheets"):
        if args.command == "candidates":
            slugs = list(args.slugs)
            if args.all_drafts:
                slugs += [s for s, d in designs.items() if d.status == "draft"]
            if args.rerolls:
                slugs += [s for s, d in designs.items() if d.notes and " reroll: " in d.notes[-1]]
        else:
            slugs = list(args.slugs)
            if args.approved_missing:
                slugs += [s for s, d in designs.items()
                          if d.status == "approved" and not _sheets_present(d, args.design_dir / s)]
        slugs = list(dict.fromkeys(slugs))
        if not slugs:
            print("nothing to do")
            return 0
        backend = backend or ComfyUIBackend(base_url=args.comfyui_url, profile="noobai", timeout=600.0)
        if not args.no_gpu_etiquette:
            _gpu_etiquette(args.comfyui_url, before=True)
        try:
            if args.command == "candidates":
                return await cmd_candidates(designs, slugs, args, backend)
            return await cmd_sheets(designs, slugs, args, backend)
        finally:
            if not args.no_gpu_etiquette:
                _gpu_etiquette(args.comfyui_url, before=False)
    if args.command == "approve":
        return cmd_approve(designs, args.slug, args.n, args.round, args)
    if args.command == "reroll":
        return cmd_reroll(designs, args.slug, args.note, args)
    if args.command == "gallery":
        return cmd_gallery(designs, args)
    return cmd_export(designs, args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
