"""Turn the grey-box guide renders into what keyframe workflows need: a lineart control image and screen regions."""

import json
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

KEY_W, KEY_H = 1216, 832


def lineart(src: Path, out: Path) -> Path:
    g = ImageOps.grayscale(Image.open(src)).filter(ImageFilter.FIND_EDGES)
    g = g.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(3))
    out.parent.mkdir(parents=True, exist_ok=True)
    g.convert("RGB").save(out)
    return out


def regions(shot_dir: Path) -> dict:
    path = shot_dir / "guide" / "regions.json"
    return json.loads(path.read_text()) if path.exists() else {}
