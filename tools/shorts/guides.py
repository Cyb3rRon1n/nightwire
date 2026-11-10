"""Turn the grey-box guide renders into what keyframe workflows need: a lineart control image and screen regions."""

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

KEY_W, KEY_H = 1216, 832


def lineart(src: Path, out: Path) -> Path:
    """White lines wherever neighbouring pixels differ in shade (> 8/255), dilated to solid ~4 px lines, specks removed."""
    g = ImageOps.grayscale(Image.open(src))
    w, h = g.size
    dx = ImageChops.difference(g, ImageChops.offset(g, 1, 0))
    dy = ImageChops.difference(g, ImageChops.offset(g, 0, 1))
    e = ImageChops.lighter(dx, dy).point(lambda v: 255 if v > 8 else 0)
    e = e.crop((0, 0, w - 1, h - 1)).filter(ImageFilter.MaxFilter(5))  # crop drops the wrapped-around border
    canvas = Image.new("L", (w, h), 0)
    canvas.paste(e, (0, 0))
    e = canvas
    e = e.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))  # open: drops specks thinner than 3 px
    out.parent.mkdir(parents=True, exist_ok=True)
    e.convert("RGB").save(out)
    return out


def regions(shot_dir: Path) -> dict:
    path = shot_dir / "guide" / "regions.json"
    return json.loads(path.read_text()) if path.exists() else {}


def visible_regions(shot_dir: Path, min_diff: float = 0.02) -> dict:
    """regions.json minus figures hidden behind the room: < 2% of pixels in the box differ between X.png and X-room.png."""
    reg, guide = regions(shot_dir), shot_dir / "guide"
    for which, boxes in reg.items():
        full, room = guide / f"{which}.png", guide / f"{which}-room.png"
        if not (full.exists() and room.exists()):
            continue
        diff = ImageChops.difference(ImageOps.grayscale(Image.open(full)), ImageOps.grayscale(Image.open(room)))
        w, h = diff.size
        keep = {}
        for fid, (x0, y0, x1, y1) in boxes.items():
            crop = diff.crop((int(x0 * w), int(y0 * h), max(int(x1 * w), int(x0 * w) + 1), max(int(y1 * h), int(y0 * h) + 1)))
            n = crop.point(lambda v: 255 if v > 8 else 0).histogram()[255]
            if n >= min_diff * crop.size[0] * crop.size[1]:
                keep[fid] = [x0, y0, x1, y1]
        reg[which] = keep
    return reg


FACE = ("nose", "reye", "leye", "rear", "lear")


def pose_json(shot_dir: Path, which: str) -> dict:
    path = shot_dir / "guide" / f"{which}-pose.json"
    return json.loads(path.read_text()) if path.exists() else {}


def pose_image(shot_dir: Path, which: str, cast) -> Path:
    """guide/<which>-pose.png: OpenPose skeletons on black for the cast figures in <which>-pose.json. A figure seen from behind
    (back: true) has no face points; limbs with a missing end are skipped."""
    from tools.reference_library import _COLOURS, _LIMBS, _ORDER
    im = Image.new("RGB", (KEY_W, KEY_H), "black")
    d = ImageDraw.Draw(im)
    for fid, fig in pose_json(shot_dir, which).items():
        if fid not in cast:
            continue
        pts = {k: (v[0] * KEY_W, v[1] * KEY_H) for k, v in fig["points"].items() if v and not (fig.get("back") and k in FACE)}
        for i, (a, b) in enumerate(_LIMBS):
            if a in pts and b in pts:
                d.line([pts[a], pts[b]], fill=tuple(int(c * .6) for c in _COLOURS[i]), width=4)
        for k, (x, y) in pts.items():
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=_COLOURS[_ORDER.index(k)])
    out = shot_dir / "guide" / f"{which}-pose.png"
    im.save(out)
    return out
