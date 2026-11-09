"""The production sheet: one page per short with everything a shot needs before money is spent, and the owner's
Approve / Change / Reject per shot (stored through the existing /designs/api/images review API)."""

import json
import re
import shutil
from pathlib import Path

from PIL import Image

from tools.shorts import approve
from tools.shorts.backends import fal
from tools.shorts.prompt import CHARACTER_SHEETS
from tools.shorts.takes import estimate

HTML = Path(__file__).with_name("sheet.html")
THUMB = 1024


def collect(short, designs, design_dir: Path, work: Path, model: str, plans: dict) -> dict:
    shots = []
    for shot in short.shots:
        report, prompt, refs = plans[shot.id]
        used, left_out = fal.usable_refs(model, refs)
        fp = approve.fingerprint(model, prompt, used)
        shots.append({
            "id": shot.id, "time": f"{shot.duration:g} s ({shot.start:g}–{shot.end:g} s)", "summary": shot.summary,
            "size": shot.size, "angle": shot.angle, "lens": shot.lens, "move": shot.move, "action": shot.action,
            "frame": shot.frame, "at_start": shot.at_start, "at_end": shot.at_end, "props": shot.props,
            "lines": [{"who": ln.who, "t": round(ln.t - shot.start, 2), "text": ln.text} for ln in shot.lines],
            "refs": [label for label, _ in used], "left_out": left_out, "cost": estimate(model, int(round(shot.duration))),
            "problems": report.problems, "warnings": report.warnings, "prompt": prompt, "fp": fp,
            "image_id": approve.plan_image_id(short.slug, shot.id, fp), "prefix": f"plan--{short.slug}--{shot.id.lower()}--",
            "still": (work / "shots" / shot.id / "still.png").exists(),
            "greybox": (work / "shots" / shot.id / "greybox.mp4").exists(),
        })
    continuity = [{"from": a["id"], "to": b["id"], "end": a["at_end"], "start": b["at_start"],
                   "flags": [p for p in b["problems"] if "props change" in p or "screen side" in p]}
                  for a, b in zip(shots, shots[1:])]
    cast = [{"id": cid, "slug": slug, "name": designs[slug].name, "lock": ", ".join(
        [*designs[slug].required, *([short.locks[cid]] if cid in short.locks else [])]),
             "sheets": [f.removesuffix(".png") for f in CHARACTER_SHEETS if (design_dir / slug / f).exists()]}
            for cid, slug in short.cast.items()]
    return {"slug": short.slug, "title": short.title, "logline": short.logline, "model": model,
            "runtime": round(sum(s.duration for s in short.shots), 1), "budget": short.budget_usd,
            "spent": round(sum(r["cost"] for r in json.loads((work / "costs.json").read_text())), 2)
            if (work / "costs.json").exists() else 0.0,
            "line_rule": short.line_rule, "style": short.style, "place": short.place,
            "beats": [{"text": b, "shot": (re.findall(r"\((S\d+)\)", b) or [""])[0]} for b in short.beats],
            "cast": cast, "shots": shots, "continuity": continuity,
            "lines": sorted(({"who": ln.who, "t": ln.t, "text": ln.text, "shot": sh.id} for sh in short.shots for ln in sh.lines),
                            key=lambda x: x["t"])}


def _thumb(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((THUMB, THUMB))
    im.save(dst, "JPEG", quality=85)


def build(data: dict, design_dir: Path, work: Path, site_root: Path) -> Path:
    site = site_root / data["slug"] / "sheet"
    site.mkdir(parents=True, exist_ok=True)
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
