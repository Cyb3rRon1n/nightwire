"""Insert library stand-ins into a room plate -> a grey draft board (labelled flat-grey figures on a darkened plate), plus the
scaled pose.json / pose.png and a depth patch (plate-sized, white = near, black = nothing) for later guided renders."""

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from tools.shorts import guides

GREY, EDGE, DIM = (128, 128, 132), (190, 190, 196), 0.55
MARGIN = 8  # depth levels (of 255) above the floor row to count as figure/prop; ponytail: tiny fixed margin, a steep top-down floor gradient may leak


def cutout(entry: Path) -> tuple[Image.Image, Image.Image, tuple[int, int], float]:
    """(mask L, depth L, feet px, figure height px) of a library cell. The floor depth is constant along a screen row, so
    figure + props (+ OTS foreground figure) are whatever is nearer than the row minimum."""
    meta = json.loads((entry / "meta.json").read_text())
    depth = np.asarray(Image.open(entry / "depth.png").convert("L"), dtype=np.int16)
    mask = depth > depth.min(axis=1, keepdims=True) + MARGIN
    mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3)))
    h, w = mask.shape
    return (Image.fromarray(mask), Image.fromarray(depth.astype(np.uint8)), (meta["feet"][0] * w, meta["feet"][1] * h), meta["figure_height_px"])


def _outline(mask: Image.Image) -> Image.Image:
    return ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(3)))


def insert_many(plate: Path, figures: list[dict], out: Path) -> Path:
    """figures: [{entry, feet: (x, y) 0..1, height: 0..1, label}]. Writes out plus <stem>.pose.json / .pose.png / .depth.png beside it."""
    out = Path(out)
    base = Image.open(plate).convert("RGB")
    W, H = base.size
    board = Image.eval(base, lambda v: int(v * DIM))
    depth = np.zeros((H, W), np.uint8)
    poses, tags = {}, []
    for f in figures:
        entry = Path(f["entry"])
        mask, dep, (fx, fy), fig_h = cutout(entry)
        s = f["height"] * H / fig_h
        size = (max(1, round(mask.width * s)), max(1, round(mask.height * s)))
        ox, oy = f["feet"][0] * W - fx * s, f["feet"][1] * H - fy * s
        pos = (round(ox), round(oy))
        m = mask.resize(size, Image.BILINEAR).point(lambda v: 255 if v > 127 else 0)
        board.paste(Image.new("RGB", size, GREY), pos, m)
        board.paste(Image.new("RGB", size, EDGE), pos, _outline(m))
        canvas = Image.new("L", (W, H), 0)
        canvas.paste(dep.resize(size, Image.BILINEAR), pos, m)
        depth = np.maximum(depth, np.asarray(canvas))
        pose = json.loads((entry / "pose.json").read_text())
        # pose points are 0..1 of the board; the whole board maps to `size` at `pos`
        pts = {k: [(ox + v[0] * size[0]) / W, (oy + v[1] * size[1]) / H] for k, v in pose["points"].items() if v}
        label = f["label"]
        while label in poses:
            label += "'"
        poses[label] = {"points": pts, "back": pose.get("back", False)}
        ys, xs = np.nonzero(np.asarray(m))
        tags.append((label, (pos[0] + (xs.min() if len(xs) else 0), pos[1] + (ys.min() if len(ys) else 0))))
    d = ImageDraw.Draw(board)
    font = ImageFont.load_default(size=18)
    for label, (x, y) in tags:
        w = round(d.textlength(label, font=font)) + 8
        x, y = min(max(x, 0), W - w), min(max(y - 24, 0), H - 24)
        d.rectangle((x, y, x + w, y + 23), fill=(20, 20, 22))
        d.text((x + 4, y + 2), label, fill=(235, 235, 240), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)
    stem = out.with_suffix("")
    Image.fromarray(depth).save(stem.with_name(stem.name + ".depth.png"))
    stem.with_name(stem.name + ".pose.json").write_text(json.dumps(poses, indent=1))
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "guide").mkdir()
        (Path(tmp) / "guide" / "p-pose.json").write_text(json.dumps(poses))
        shutil.copy(guides.pose_image(Path(tmp), "p", set(poses)), stem.with_name(stem.name + ".pose.png"))
    pp = stem.with_name(stem.name + ".pose.png")
    Image.open(pp).resize((W, H)).save(pp)
    return out


def insert(plate: Path, entry: Path, feet_xy: tuple[float, float], height_frac: float, label: str, out: Path) -> Path:
    return insert_many(plate, [{"entry": entry, "feet": feet_xy, "height": height_frac, "label": label}], out)
