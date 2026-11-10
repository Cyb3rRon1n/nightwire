"""The per-short page: stage tabs (Bible, Plates, Keyframes, Shots, Takes, Cut), each with its gate status, and
everything a shot needs before money is spent. Read-only: decisions happen in the review inbox at /review/."""

import hashlib
import json
import re
import shutil
from pathlib import Path

from PIL import Image

from tools.shorts import approve, keyframes, plates as plate_mod
from tools.shorts.backends import fal
from tools.shorts.prompt import CHARACTER_SHEETS
from tools.shorts.takes import estimate

HTML = Path(__file__).with_name("sheet.html")
THUMB = 1024


STAGES = ("Bible", "Plates", "Keyframes", "Shots", "Takes", "Cut")


def cut_id(slug: str, cut: Path) -> str:
    """Versioned by the file's bytes: a keep on an old cut never approves a new one."""
    return f"cut--{slug}--{hashlib.sha256(cut.read_bytes()).hexdigest()[:10]}"


def cut_file(work: Path) -> Path | None:
    return next((p for p in (work / "cut.mp4", work / "draft.mp4") if p.exists()), None)


def stages(short, plans: list[dict], plates: dict, approvals: dict, work: Path) -> list[dict]:
    """Gate status per stage; a stage is locked until every earlier one is approved. plans = collect()'s shot rows."""
    images = approvals.get("images", {})
    keep = lambda v: (v or {}).get("verdict") == "keep"  # noqa: E731
    named = sorted({sh.plate for sh in short.shots if sh.plate})
    i2v = [sh for sh in short.shots if sh.mode == "i2v"]
    keys = [(sh, w) for sh in i2v for w in keyframes.needed(sh)]
    kept_takes = [sh for sh in short.shots if any(
        (v or {}).get("verdict") == "keep" for v in _verdicts(work, sh.id).values())]
    cut = cut_file(work)
    checks = [
        ("Bible", short.scene is not None and keep(approvals.get("SCENE", {}).get(approve.scene_fp(short))),
         "the scene, wardrobe and seating"),
        ("Plates", bool(named) and all(n in plates and keep(images.get(plate_mod.plate_id(short.place, n))) for n in named),
         f"{len(named)} room view(s)"),
        ("Keyframes", all(keyframes.chosen_path(work, sh.id, w).exists()
                          and keep(images.get(f"key--{short.slug}--{sh.id.lower()}--{w}")) for sh, w in keys),
         f"{len(keys)} opening/closing picture(s)"),
        ("Shots", all(keep(approvals.get(p["id"], {}).get(p["fp"])) for p in plans), f"{len(plans)} shot plan(s)"),
        ("Takes", len(kept_takes) == len(short.shots), f"{len(short.shots)} shot(s) need a chosen take"),
        ("Cut", cut is not None and keep(images.get(cut_id(short.slug, cut))), "the assembled film"),
    ]
    out, open_ = [], True
    for name, ok, detail in checks:
        status = "locked" if not open_ else "approved" if ok else "waiting"
        out.append({"name": name, "status": status, "detail": detail})
        open_ = open_ and ok
    return out


def _verdicts(work: Path, shot_id: str) -> dict:
    f = work / "shots" / shot_id / "verdicts.json"
    return json.loads(f.read_text()) if f.exists() else {}


def collect(short, designs, design_dir: Path, work: Path, default: str, plans: dict, approvals: dict | None = None, plates_root: Path | None = None) -> dict:
    costs = json.loads((work / "costs.json").read_text()) if (work / "costs.json").exists() else []
    shots = []
    for shot in short.shots:
        report, prompt, refs = plans[shot.id]
        model = fal.shot_model(shot, default)
        used, left_out = fal.usable_refs(model, refs)
        fp = approve.fingerprint(model, prompt, used, int(round(shot.duration)), approve.fp_extra(short, shot, design_dir, plates_root))
        shots.append({
            "id": shot.id, "time": f"{shot.duration:g} s ({shot.start:g}–{shot.end:g} s)", "summary": shot.summary,
            "size": shot.size, "angle": shot.angle, "lens": shot.lens, "move": shot.move, "action": shot.action,
            "frame": shot.frame, "at_start": shot.at_start, "at_end": shot.at_end, "props": shot.props,
            "lines": [{"who": ln.who, "t": round(ln.t - shot.start, 2), "text": ln.text} for ln in shot.lines],
            "refs": [label for label, _ in used], "left_out": left_out, "model": model, "cost": estimate(model, int(round(shot.duration))),
            "problems": report.problems, "warnings": report.warnings, "prompt": prompt, "fp": fp,
            "image_id": approve.plan_image_id(short.slug, shot.id, fp), "prefix": f"plan--{short.slug}--{shot.id.lower()}--",
            "still": (work / "shots" / shot.id / "still.png").exists(),
            "greybox": (work / "shots" / shot.id / "greybox.mp4").exists(),
            "overrides": [r["note"] for r in costs if r.get("shot") == shot.id and r.get("note")],
        })
    continuity = [{"from": a["id"], "to": b["id"], "end": a["at_end"], "start": b["at_start"],
                   "flags": [p for p in b["problems"] if "props change" in p or "screen side" in p]}
                  for a, b in zip(shots, shots[1:])]
    cast = [{"id": cid, "slug": slug, "name": designs[slug].name, "lock": ", ".join(
        [*designs[slug].required, *([short.locks[cid]] if cid in short.locks else [])]),
             "sheets": [f.removesuffix(".png") for f in CHARACTER_SHEETS if (design_dir / slug / f).exists()]}
            for cid, slug in short.cast.items()]
    catalogue = plate_mod.load_plates(short.place, plates_root)
    approvals = approvals or {"images": {}}
    kf = {sh.id: [w for w in keyframes.needed(sh) if keyframes.chosen_path(work, sh.id, w).exists()] for sh in short.shots}
    from tools.shorts.model import scene_text
    return {"slug": short.slug, "title": short.title, "logline": short.logline, "model": default,
            "runtime": round(sum(s.duration for s in short.shots), 1), "budget": short.budget_usd,
            "spent": round(sum(r["cost"] for r in costs), 2),
            "line_rule": short.line_rule, "style": short.style, "place": short.place,
            "beats": [{"text": b, "shot": (re.findall(r"\((S\d+)\)", b) or [""])[0]} for b in short.beats],
            "cast": cast, "shots": shots, "stages": stages(short, shots, catalogue, approvals, work),
            "bible": {"scene": scene_text(short) if short.scene else "", "wardrobe": dict(short.wardrobe), "blocking": dict(short.blocking)},
            "plates": [{"name": n, "view": catalogue[n].view,
                        "img": plate_path_ok(design_dir, short.place, catalogue[n])} for n in sorted({sh.plate for sh in short.shots} & set(catalogue))],
            "keyframes": kf, "continuity": continuity,
            "lines": sorted(({"who": ln.who, "t": ln.t, "text": ln.text, "shot": sh.id} for sh in short.shots for ln in sh.lines),
                            key=lambda x: x["t"])}


def plate_path_ok(design_dir, place, plate) -> bool:
    return plate_mod.plate_path(design_dir, place, plate).exists()


def _thumb(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((THUMB, THUMB))
    im.save(dst, "JPEG", quality=85)


def build(data: dict, design_dir: Path, work: Path, site_root: Path) -> Path:
    site = site_root / data["slug"]
    site.mkdir(parents=True, exist_ok=True)
    (site / "sheet").mkdir(exist_ok=True)  # old links and homelab tiles point here
    (site / "sheet" / "index.html").write_text('<!doctype html><meta http-equiv="refresh" content="0; url=../">')
    for p in data["plates"]:
        if p["img"]:
            cat = plate_mod.load_plates(data["place"])[p["name"]]
            _thumb(plate_mod.plate_path(design_dir, data["place"], cat), site / "plates" / f"{p['name']}.jpg")
    for sid, whiches in data["keyframes"].items():
        for w in whiches:
            try:
                _thumb(keyframes.chosen_path(work, sid, w), site / "keyframes" / f"{sid}-{w}.jpg")
            except OSError:
                pass  # an unreadable picture just shows no thumbnail
    for c in data["cast"]:
        for name in c["sheets"]:
            _thumb(design_dir / c["slug"] / f"{name}.png", site / "cast" / f"{c['slug']}-{name}.jpg")
    if (design_dir / data["place"] / "play.png").exists():
        _thumb(design_dir / data["place"] / "play.png", site / "place.jpg")
    if (work / "floorplan.png").exists():
        _thumb(work / "floorplan.png", site / "floorplan.jpg")
    for s in data["shots"]:
        sd = work / "shots" / s["id"]
        if s["still"]:
            _thumb(sd / "still.png", site / "shots" / f"{s['id']}-still.jpg")
        if s["greybox"]:
            (site / "shots").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sd / "greybox.mp4", site / "shots" / f"{s['id']}-greybox.mp4")
    (site / "sheet.json").write_text(json.dumps(data, indent=1))
    shutil.copyfile(HTML, site / "index.html")
    return site
