"""Phase 19b design studio CLI: render, approve and export Kuroshio's
character model sheets and location designs.

    python -m tools.design_studio candidates mama-sato | --all-drafts | --rerolls
    python -m tools.design_studio approve mama-sato 3
    python -m tools.design_studio reroll mama-sato "older, thinner"
    python -m tools.design_studio sheets mama-sato | --approved-missing
    python -m tools.design_studio gallery
    python -m tools.design_studio export

Runbook: the owner picks at http://192.168.10.19:8080/designs/ (see
docs/design-studio-resume.md). `approve` defaults to the round the last gallery showed,
else the latest; pass `--round <r>` to override.
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

from narrator.comfyui_backend import ComfyUIBackend
from narrator.design_sheets import (
    CHARACTER_SHEETS, EXPRESSION_SIZE, LOCATION_SHEETS, MOOD_SUFFIXES, candidate_prompt, candidate_workflow,
    expression_grid, expression_prompts, extract_palette, join_strip, sheet_prompt, sheet_workflow,
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
    if round_no is None:  # approve the round the owner saw in the gallery
        try:
            round_no = json.loads((args.design_dir / "gallery" / "rounds.json").read_text()).get(slug)
        except (OSError, ValueError):
            pass
    r, cands = _latest_candidates(args.design_dir / slug, round_no)
    print(f"{slug}: using round {r}")
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
        if getattr(args, "only", None) not in (None, sheet):
            continue
        if sheet == "moodkeys":
            frames = []
            for mood in MOOD_SUFFIXES:
                pos, neg = sheet_prompt(d, sheet, mood=mood)
                frames.append(await backend.run_workflow(sheet_workflow(pos, neg, d.seed, high_res=False)))
            png = join_strip(frames)
        elif sheet == "expressions":
            panels = []
            for label, pos, neg in expression_prompts(d):
                wf = candidate_workflow(pos, neg, d.seed)
                wf["5"]["inputs"].update(width=EXPRESSION_SIZE[0], height=EXPRESSION_SIZE[1])
                panels.append((label, await backend.run_workflow(wf)))
            png = expression_grid(panels)
        else:
            pos, neg = sheet_prompt(d, sheet)
            png = await backend.run_workflow(sheet_workflow(pos, neg, d.seed))
        (slug_dir / f"{sheet}.png").write_bytes(png)
        print(f"{slug}: {sheet}", flush=True)
    key = "turnaround" if d.kind == "character" else "establishing"
    if (slug_dir / f"{key}.png").exists():
        d.palette = extract_palette((slug_dir / f"{key}.png").read_bytes(), skip_background=d.kind == "character")
    save_design(d, args.designs_dir / f"{slug}.toml")


def _sheets_present(d: Design, slug_dir: Path) -> bool:
    sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
    return all((slug_dir / f"{s}.png").exists() for s in sheets)


def _web_copy(src: Path, dest: Path) -> None:
    from PIL import Image
    im = Image.open(src).convert("RGB")
    im.thumbnail((1100, 1100))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=84)


GALLERY_STYLE = """
:root{color-scheme:dark;--bg:#0d0b14;--panel:#16121f;--text:#e9e4f2;--dim:#a79fb8;--line:#3de8ff55;--pink:#ff3d9a;--pick:#ffe14d}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif;margin:0 auto;padding:0 24px 48px;max-width:1500px}
a{color:#3de8ff}
#bar{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;min-height:52px;padding:8px 0;background:#0d0b14f2;border-bottom:1px solid var(--line);font-weight:600}
#bar .err{color:#ff8a8a}
h1{margin:24px 0 2px;font-size:1.7rem}
.lede{color:var(--dim);margin:0 0 8px}
h2.group{font-size:1.3rem;color:var(--pink);border-bottom:1px solid var(--line);margin:28px 0 0;padding-bottom:4px}
details.group>summary{font-size:1.3rem;font-weight:700;color:var(--pink);border-bottom:1px solid var(--line);margin-top:36px;padding:6px 0;cursor:pointer}
section{margin:22px 0 34px;scroll-margin-top:64px}
section.decided h3::after{content:"  ✓";color:var(--pick)}
h3{font-size:1.2rem;margin:0}
h3 small{color:var(--dim);font-size:.8rem;font-weight:400;margin-left:6px}
.role{color:var(--dim);margin:0 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:10px}
figure{margin:0;background:var(--panel);outline:3px solid transparent;outline-offset:-1px;display:flex;flex-direction:column}
figure.picked{outline-color:var(--pick)}
img{width:100%;height:auto;display:block}
button.zoom{all:unset;display:block;cursor:zoom-in;aspect-ratio:3/2;background:#000}
button.zoom:focus-visible{outline:2px solid #3de8ff;outline-offset:-2px}
button.zoom img{height:100%;object-fit:contain}
figcaption{padding:8px;color:var(--pick);display:flex;align-items:center;justify-content:space-between;gap:8px;flex:1}
button,input{font:600 14px system-ui,sans-serif;min-height:40px}
button{background:#16121f;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:0 14px;cursor:pointer}
button:hover:not(:disabled){border-color:#3de8ff}
button:focus-visible,input:focus-visible{outline:2px solid #3de8ff;outline-offset:1px}
button:disabled,input:disabled{opacity:.45;cursor:default}
button.pick{flex:1}
button.pick[aria-pressed=true],.ctl button.on{background:var(--pick);border-color:var(--pick);color:#0d0b14}
.ctl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
.ctl input{flex:1 1 240px;min-width:0;max-width:520px;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:0 10px;font-weight:400}
.state{color:var(--dim);font-size:13px;overflow-wrap:anywhere}
details.more{margin-top:8px;color:var(--dim);font-size:13px}
details.more summary{cursor:pointer}
.tags{font:12px/1.5 ui-monospace,monospace}
details.more ul{margin:6px 0;padding-left:18px}
dialog{background:var(--bg);color:var(--text);border:1px solid var(--line);padding:12px;width:min(96vw,1500px);max-height:96vh}
dialog::backdrop{background:#000c}
dialog[open]{display:flex;flex-direction:column;gap:10px}
.zoom-top,.zoom-nav{display:flex;align-items:center;justify-content:space-between;gap:10px}
.zoom-nav{justify-content:center}
.zoom-nav .pick{flex:0 1 220px}
#zoom-img{flex:1;min-height:0;width:100%;max-height:calc(96vh - 130px);object-fit:contain}
@media(max-width:600px){body{padding:0 16px 32px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}button.pick{padding:0 6px}}
"""


def _gallery_section(slug: str, d: Design, r: int, figs: list[str], pick: bool) -> str:
    name = html.escape(d.name)
    role = next((n.split("draft:", 1)[1].strip() for n in d.notes if "draft:" in n), "")
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in d.notes[-3:])
    attrs = f'data-slug="{html.escape(slug)}" data-name="{name}" data-round="{r}"' + (" data-pick" if pick else "")
    return (f'<section {attrs}><h3>{name} <small>{d.kind} · round {r}</small></h3>'
            + (f'<p class="role">{html.escape(role)}</p>' if role else "")
            + f'<div class="grid">{"".join(figs)}</div>'
            f'<details class="more"><summary>Prompt tags and history</summary>'
            f'<p class="tags">{html.escape(d.tags)}</p><ul>{notes}</ul></details></section>')


def _approved_candidate(d: Design, slug_dir: Path) -> tuple[int, int, Path] | None:
    won = [m for note in d.notes for m in re.findall(r"approved r(\d+) #(\d+)", note)]
    if not won:
        return None
    r, n = map(int, won[-1])
    return r, n, _latest_candidates(slug_dir, r)[1].get(n)


def _review_page(designs, args, out: Path) -> dict[str, str]:
    """review/index.html: the approved art beside each sheet's old and new version, with the checker's flags.
    Returns {slug: sheet version}, so the dashboard can count what's still unreviewed."""
    report_path = args.design_dir / "qa" / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    cards, versions = [], {}
    for slug, d in sorted(designs.items()):
        slug_dir = args.design_dir / slug
        sheet = slug_dir / "expressions.png"
        if d.kind != "character" or d.status != "approved" or not sheet.exists():
            continue
        name = html.escape(d.name)
        figures = []
        won = _approved_candidate(d, slug_dir)
        if won and won[2]:
            figures.append(("Approved design", f"r{won[0]}-c{won[1]}.jpg", won[2]))
        for s, title in (("expressions", "Expressions"), ("turnaround", "Turnaround"), ("colorguide", "Colour guide")):
            if (slug_dir / f"{s}-old.png").exists():
                figures.append((f"{title}: before", f"{s}-old.jpg", slug_dir / f"{s}-old.png"))
            if (slug_dir / f"{s}.png").exists():
                figures.append((f"{title}: now", f"{s}.jpg", slug_dir / f"{s}.png"))
        figs = []
        for label, rel, src in figures:
            _web_copy(src, out / "img" / slug / rel)
            figs.append(f'<figure><a href="../img/{slug}/{rel}" target="_blank" rel="noopener"><img src="../img/{slug}/{rel}" '
                        f'alt="{name}: {label}" loading="lazy"></a><figcaption>{label}</figcaption></figure>')
        entry = report.get(slug)
        flags = entry["flags"] if entry else []
        if entry is None:
            check = '<p class="state">Not checked yet.</p>'
        elif flags:
            check = '<ul class="flags">' + "".join(f"<li>{html.escape(f)}</li>" for f in flags) + "</ul>"
        else:
            check = '<p class="state">The automatic check found nothing. It can miss small details, so still look.</p>'
        unchecked = entry["unchecked"] if entry else []
        if unchecked:
            check += f'<p class="state">Too small or specific to check: {html.escape(", ".join(unchecked))}</p>'
        versions[slug] = str(max((slug_dir / f"{s}.png").stat().st_mtime_ns for s in CHARACTER_SHEETS if (slug_dir / f"{s}.png").exists()))
        cards.append((not flags, f'<section data-slug="{html.escape(slug)}" data-v="{versions[slug]}"><h3>{name}</h3>'
                      f'<div class="grid">{"".join(figs)}</div>{check}<div class="ctl">'
                      '<button type="button" class="ok">Looks right</button><input type="text" maxlength="500" '
                      f'aria-label="What needs fixing on {name}" placeholder="What needs fixing?">'
                      '<button type="button" class="fix">Needs a fix</button><span class="state" role="status"></span></div></section>'))
    body = "".join(c for _, c in sorted(cards, key=lambda c: c[0]))
    template = Path(__file__).with_name("design_review.html").read_text()
    (out / "review").mkdir(parents=True, exist_ok=True)
    (out / "review" / "index.html").write_text(template.replace("/*STYLE*/", GALLERY_STYLE).replace("<!--CARDS-->", body))
    return versions


def cmd_gallery(designs, args) -> int:
    out = args.design_dir / "gallery"
    groups: dict[str, list[str]] = {"candidates": [], "approved": [], "other": []}
    rounds = {}
    for slug, d in sorted(designs.items()):
        slug_dir = args.design_dir / slug
        r, cands = _latest_candidates(slug_dir)
        if cands:
            rounds[slug] = r
        pick = d.status == "candidates" and bool(cands)
        name = html.escape(d.name)
        figs = []
        for n, p in sorted(cands.items()):
            rel = f"img/{slug}/r{r}-c{n}.jpg"
            _web_copy(p, out / rel)
            won = d.status == "approved" and any(re.search(rf"approved r{r} #{n}\b", note) for note in d.notes)
            button = f'<button type="button" class="pick">Pick #{n}</button>' if pick else f"#{n}" + (" ✓ approved" if won else "")
            figs.append(f'<figure data-n="{n}"><button type="button" class="zoom" aria-label="Enlarge {name} candidate {n}">'
                        f'<img src="{rel}" alt="{name} candidate {n}" loading="lazy"></button><figcaption>{button}</figcaption></figure>')
        sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
        for s in sheets:
            if (slug_dir / f"{s}.png").exists():
                rel = f"img/{slug}/{s}.jpg"
                _web_copy(slug_dir / f"{s}.png", out / rel)
                figs.append(f'<figure><button type="button" class="zoom" aria-label="Enlarge {name} {s}">'
                            f'<img src="{rel}" alt="{name} {s}" loading="lazy"></button><figcaption>{s}</figcaption></figure>')
        group = "candidates" if pick else "approved" if d.status == "approved" else "other"
        groups[group].append(_gallery_section(slug, d, r, figs, pick))
    body = '<div id="bar" role="status">Loading picks…</div><h1>Kuroshio Design Studio</h1>'
    body += '<p class="lede"><a href="/">← AI Lab</a> · <a href="review/">Review sheets</a> · Tap an image to see it full size. Pick one for each character, or ask for a reroll with a note. Picks save as you go.</p>'
    if groups["candidates"]:
        body += f'<h2 class="group">Needs your pick ({len(groups["candidates"])})</h2>' + "".join(groups["candidates"])
    if groups["other"]:
        body += f'<h2 class="group">In progress ({len(groups["other"])})</h2>' + "".join(groups["other"])
    if groups["approved"]:
        body += (f'<details class="group"><summary>Approved ({len(groups["approved"])})</summary>'
                 + "".join(groups["approved"]) + "</details>")
    picker = Path(__file__).with_name("design_picker.html").read_text()
    page = ('<!doctype html><html lang="en"><meta charset=utf-8>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Kuroshio Design Studio</title><style>{GALLERY_STYLE}</style><body>{body}{picker}</body></html>")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page)
    (out / "rounds.json").write_text(json.dumps(rounds))
    needs_pick = sorted(s for s, d in designs.items() if d.status == "candidates" and s in rounds)
    review = _review_page(designs, args, out)
    (out / "status.json").write_text(json.dumps({"needs_pick": {s: rounds[s] for s in needs_pick}, "review": review}))  # dashboard badges
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
    s.add_argument("--only", choices=(*CHARACTER_SHEETS, *LOCATION_SHEETS), help="redo just this sheet; keeps the others")
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
