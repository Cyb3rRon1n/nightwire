"""One function per kind of reviewable work. Each returns Items; registry.build_items collects them.
URLs point at pages already published on the AI Lab box (/designs, /world, /shorts) or at copies made with web_copy."""

import json
from pathlib import Path

from narrator.design_sheets import CHARACTER_SHEETS
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
        judged = [folder / f"{s}.png" for s in CHARACTER_SHEETS if (folder / f"{s}.png").exists()]
        if not judged:
            continue
        version = str(max(f.stat().st_mtime_ns for f in judged))  # = design_studio._review_page (props not counted)
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
