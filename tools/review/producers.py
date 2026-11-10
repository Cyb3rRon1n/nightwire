"""One function per kind of reviewable work. Each returns Items; registry.build_items collects them.
URLs point at pages already published on the AI Lab box (/designs, /world, /shorts) or at copies made with web_copy."""

import hashlib
import json
import shutil
from pathlib import Path

from narrator.design_sheets import CHARACTER_SHEETS
from tools.review.registry import Item, web_copy

SHEETS = (("portrait", "Portrait"), ("expressions", "Expressions"), ("turnaround", "Turnaround"),
          ("colorguide", "Colour guide"), ("props", "Hands and props"))


PICK_FIRST = "Claude picks one candidate first; approve the chosen one"  # candidates are shown so the owner can see them, but only the chosen file is approvable


def sheet_id(slug: str, version: str) -> str:
    return f"sheet--{slug}--{version}"


def sheets(ctx) -> list[Item]:
    out = []
    for slug, d in sorted(ctx["designs"].items()):
        folder = ctx["design_dir"] / slug
        now = [(s, t) for s, t in SHEETS if (folder / f"{s}.png").exists()]
        if d.kind != "character" or d.status != "approved" or not now or getattr(d, "wardrobe", None):
            continue  # characters with wardrobe states are reviewed through bibles/sheet_sets instead
        judged = [folder / f"{s}.png" for s in CHARACTER_SHEETS if (folder / f"{s}.png").exists()]
        if not judged:
            continue
        version = str(max(f.stat().st_mtime_ns for f in judged))  # = design_studio._review_page (props not counted)
        files = [web_copy(folder / f"{s}.png", ctx["site"], f"sheets/{slug}/{s}.jpg") for s, _ in now]
        compare = [{"label": f"{t}: before", "url": web_copy(folder / f"{s}-old.png", ctx["site"], f"sheets/{slug}/{s}-old.jpg")}
                   for s, t in SHEETS if (folder / f"{s}-old.png").exists()]
        out.append(Item(sheet_id(slug, version), "sheet", "designs", slug, f"{d.name}: model sheets", files, compare))
    return out


def _bible_data(d) -> dict:
    return {"identity": list(d.identity), "appearance": d.appearance,
            "wardrobe": {k: {"text": w.text, "tags": w.tags, "props": list(w.props)} for k, w in sorted(d.wardrobe.items())}}


def bible_id(d, slug: str) -> str:
    """Changes whenever the bible text does, so a keep on old text never approves new text."""
    blob = json.dumps(_bible_data(d), sort_keys=True, ensure_ascii=False)
    return f"bible--{slug}--{hashlib.sha256(blob.encode()).hexdigest()[:10]}"


def bible_text(d) -> str:
    lines = ["Identity:", *[f"- {i}" for i in d.identity], f"Appearance: {d.appearance}"]
    for k, w in sorted(d.wardrobe.items()):
        lines += [f"State {k}: {w.text}", f"  tags: {w.tags}", f"  props: {', '.join(w.props)}"]
    return "\n".join(lines)


def bibles(ctx) -> list[Item]:
    out = []
    for slug, d in sorted(ctx["designs"].items()):
        if d.kind != "character" or not (getattr(d, "identity", None) or getattr(d, "wardrobe", None)):
            continue
        folder = ctx["design_dir"] / slug
        files = [web_copy(folder / f"{s}.png", ctx["site"], f"bibles/{slug}/{s}.jpg")
                 for s in ("turnaround", "portrait") if (folder / f"{s}.png").exists()]
        text = bible_text(d)
        dec = ctx["design_dir"] / "bibles" / f"{slug}-decisions.md"
        if dec.exists():
            text += "\n\nOpen decisions (answer in the Fix note):\n" + dec.read_text()
        out.append(Item(bible_id(d, slug), "bible", "designs", slug, f"{d.name}: character bible (text)", files, context=text))
    return out


SET_ORDER = ("turnaround", "portrait", "expressions", "props")


def sheet_set_id(slug: str, state: str, folder: Path) -> str:
    h = hashlib.sha256()
    for s in SET_ORDER:
        h.update((folder / f"{s}.png").read_bytes())
    return f"sheet--{slug}--{state}--{h.hexdigest()[:10]}"


def sheet_sets(ctx) -> list[Item]:
    out = []
    for slug, d in sorted(ctx["designs"].items()):
        for state, w in sorted((getattr(d, "wardrobe", None) or {}).items()):
            folder = ctx["design_dir"] / slug / "wardrobe" / state
            if not all((folder / f"{s}.png").exists() for s in SET_ORDER):
                continue
            names = [*SET_ORDER, "colorguide"]
            files = [web_copy(folder / f"{s}.png", ctx["site"], f"sheets/{slug}/{state}/{s}.jpg")
                     for s in names if (folder / f"{s}.png").exists()]
            top = ctx["design_dir"] / slug
            compare = [{"label": f"{s.capitalize()}: original", "url": web_copy(top / f"{s}.png", ctx["site"], f"sheets/{slug}/{state}/orig-{s}.jpg")}
                       for s in ("turnaround", "portrait") if (top / f"{s}.png").exists()]
            context = "\n".join(["Identity:", *[f"- {i}" for i in d.identity], f"State {state}: {w.text}"])
            out.append(Item(sheet_set_id(slug, state, folder), "sheet-set", "designs", slug,
                            f"{d.name}: {state} sheet set", files, compare, context=context))
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
            picked = chosen.exists()
            out.append(Item(pl.plate_id(short.place, plate.name, chosen), "plate", "pre-production", short.place,
                            f"{short.place}: plate {plate.name}", files, compare,
                            context=plate.view if picked else f"{PICK_FIRST}\n{plate.view}", **({} if picked else {"choices": ()})))
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


def keyframes(ctx) -> list[Item]:
    from tools.shorts import approve
    from tools.shorts import keyframes as kf
    from tools.shorts import plates as pl
    out = []
    for short in _shorts(ctx):
        work = ctx["design_dir"] / "shorts" / short.slug
        catalogue = pl.load_plates(short.place, ctx.get("plates_root"))
        for shot in short.shots:
            for which in kf.needed(shot):
                chosen = kf.chosen_path(work, shot.id, which)
                srcs = [chosen] if chosen.exists() else sorted((work / "shots" / shot.id / "keyframes").glob(f"{which}-c*.png"))[:6]
                if not srcs:
                    continue
                rel = f"keyframes/{short.slug}/{shot.id.lower()}"
                files = [web_copy(f, ctx["site"], f"{rel}/{f.stem}.jpg") for f in srcs]
                compare = []
                for cid in shot.frame:
                    if cid not in short.cast:
                        continue
                    folder = ctx["design_dir"] / short.cast[cid]
                    turn = folder / "shorts" / "turnaround.png"
                    for label, f in ((f"{cid} turnaround", turn if turn.exists() else folder / "turnaround.png"),
                                     (f"{cid} portrait", folder / "portrait.png")):
                        if f.exists():
                            compare.append({"label": label, "url": web_copy(f, ctx["site"], f"{rel}/{cid}-{f.stem}.jpg")})
                if shot.plate in catalogue:
                    plate = pl.plate_path(ctx["design_dir"], short.place, catalogue[shot.plate])
                    if plate.exists():
                        compare.append({"label": "Plate", "url": web_copy(plate, ctx["site"], f"{rel}/plate.jpg")})
                guide = work / "shots" / shot.id / "guide" / f"{which}.png"
                if guide.exists():
                    compare.append({"label": "Grey-box", "url": web_copy(guide, ctx["site"], f"{rel}/{which}-greybox.jpg")})
                moves = shot.at_start if which == "start" else shot.at_end
                context = "\n".join([f"Frame {k}: {v}" for k, v in sorted(shot.frame.items())]
                                    + [f"At {which} {k}: {v}" for k, v in sorted(moves.items())]
                                    + [f"Props {k}: {v}" for k, v in sorted(shot.props.items())]
                                    + [f"Wardrobe {k}: {v}" for k, v in sorted(short.wardrobe.items())])
                if not chosen.exists():
                    context = f"{PICK_FIRST}\n{context}"
                out.append(Item(approve.keyframe_id(short.slug, shot.id, which, chosen), "keyframe", "pre-production", short.slug,
                                f"{short.title}: {shot.id} {which} keyframe", files, compare, context=context,
                                **({} if chosen.exists() else {"choices": ()})))
    return out


def plans(ctx) -> list[Item]:
    """One item per shot plan that is ready to approve: its only pre-flight problems are approvals still pending."""
    from tools.shorts import __main__ as cli
    from tools.shorts import sheet
    from tools.shorts.backends import fal
    out = []
    images = ctx.get("images") or {}
    for short in _shorts(ctx):
        if not short.model or short.model not in fal.MODELS:
            continue
        work = ctx["design_dir"] / "shorts" / short.slug
        pre = {shot.id: cli._preflight(short, shot, fal.shot_model(shot, short.model), ctx["designs"], images,
                                           ctx["design_dir"], ctx.get("plates_root")) for shot in short.shots}
        data = sheet.collect(short, ctx["designs"], ctx["design_dir"], work, short.model, pre, cli._approvals(work, images),
                              ctx.get("plates_root"))
        for row in data["shots"]:
            if any("not approved" not in p for p in row["problems"]):
                continue
            sd = work / "shots" / row["id"]
            src = next((f for f in (sd / "keyframe-start.png", sd / "preview" / "start.png") if f.exists()), None)
            files = [web_copy(src, ctx["site"], f"plans/{short.slug}/{row['id'].lower()}.jpg")] if src else []
            context = "\n".join([f"Model: {row['model']}", f"Cost: about ${row['cost']:.2f}", *[f"Waiting on: {p}" for p in row["problems"]],
                                 "Prompt:", row["prompt"]])
            out.append(Item(row["image_id"], "plan", "pre-production", short.slug, f"{short.title}: {row['id']} plan", files, context=context))
    return out


def cuts(ctx) -> list[Item]:
    from tools.shorts import sheet
    out = []
    for short in _shorts(ctx):
        f = sheet.cut_file(ctx["design_dir"] / "shorts" / short.slug)
        if f:
            dst = ctx["site"] / "media" / "cuts" / short.slug / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or (dst.stat().st_size, dst.stat().st_mtime_ns) != (f.stat().st_size, f.stat().st_mtime_ns):
                shutil.copy2(f, dst)  # a video: web_copy makes JPEGs; copy2 keeps mtime so the next run skips it
            out.append(Item(sheet.cut_id(short.slug, f), "cut", "finished", short.slug, f"{short.title}: cut",
                            [f"/review/media/cuts/{short.slug}/{f.name}"]))
    return out


ALL = [sheets, bibles, sheet_sets, candidates, world, takes, wallpapers, plates, scenes, keyframes, plans, cuts]
