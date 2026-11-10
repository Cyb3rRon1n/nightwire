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


def _shorts(ctx):
    from tools.shorts import SHORTS_DIR
    from tools.shorts.model import load_short
    root = Path(ctx.get("shorts_dir") or SHORTS_DIR)
    return [load_short(p.parent) for p in sorted(root.glob("*/short.toml"))]


def plates(ctx) -> list[Item]:
    from tools.shorts import plates as pl
    out, seen = [], set()
    for short in _shorts(ctx):
        catalogue = pl.load_plates(short.place, ctx.get("plates_root"))
        base = ctx["design_dir"] / short.place
        for shot in short.shots:
            plate = catalogue.get(shot.plate)
            if plate is None or (short.place, plate.name) in seen:
                continue
            seen.add((short.place, plate.name))
            chosen = pl.plate_path(ctx["design_dir"], short.place, plate)
            srcs = [chosen] if chosen.exists() else sorted((base / "plates").glob(f"{plate.name}-c*.png"))
            if not srcs:
                continue
            rel = f"plates/{short.place}"
            files = [web_copy(f, ctx["site"], f"{rel}/{f.stem}.jpg") for f in srcs]
            compare = ([{"label": "Approved room", "url": web_copy(base / "play.png", ctx["site"], f"{rel}/play.jpg")}]
                       if (base / "play.png").exists() else [])
            out.append(Item(pl.plate_id(short.place, plate.name), "plate", "pre-production", short.place,
                            f"{short.place}: plate {plate.name}", files, compare, context=plate.view))
    return out


def scenes(ctx) -> list[Item]:
    from tools.shorts.approve import scene_fp
    from tools.shorts.model import scene_text
    out = []
    for s in _shorts(ctx):
        if s.scene is None:
            continue
        play = ctx["design_dir"] / s.place / "play.png"
        files = [web_copy(play, ctx["site"], f"plates/{s.place}/play.jpg")] if play.exists() else []
        context = "\n".join([scene_text(s)] + [f"Wardrobe {k}: {v}" for k, v in sorted(s.wardrobe.items())]
                            + [f"Blocking {k}: {v}" for k, v in sorted(s.blocking.items())])
        out.append(Item(f"plan--{s.slug}--scene--{scene_fp(s)}", "scene", "pre-production", s.slug,
                        f"{s.title}: scene", files, context=context))
    return out


ALL = [sheets, candidates, world, takes, wallpapers, plates, scenes]
