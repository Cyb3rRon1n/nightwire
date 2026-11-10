"""Turn the grey-box guide renders into what keyframe workflows need: a lineart control image and screen regions."""

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

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
