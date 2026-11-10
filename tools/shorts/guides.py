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
    e = e.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))  # open: drops specks thinner than 3 px
    out.parent.mkdir(parents=True, exist_ok=True)
    e.convert("RGB").save(out)
    return out


def regions(shot_dir: Path) -> dict:
    path = shot_dir / "guide" / "regions.json"
    return json.loads(path.read_text()) if path.exists() else {}
