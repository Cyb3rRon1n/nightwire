"""Insert library stand-ins into a room plate -> a grey draft board (labelled flat-grey figures on a darkened plate), plus the
scaled pose.json / pose.png and a depth patch (plate-sized, white = near, black = nothing) for later guided renders."""

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from tools.shorts import guides

FIGURE, PROPS, FOREGROUND, EDGE, DIM = (150, 150, 155), (105, 105, 110), (90, 90, 95), (200, 200, 206), 0.55
FG_GAP = 20  # an OTS foreground figure is at least this much nearer than the whole figure; props in front of it are less
MARGIN = 4  # depth levels (of 255) a pixel must be nearer than the empty floor to count as an object


def _depth(entry: Path, name: str) -> np.ndarray:
    return np.asarray(Image.open(entry / name).convert("L"), dtype=np.int16)


def cutout(entry: Path) -> dict:
    """Exact masks of a library cell, cropped to their union box: {"layers": [(mask, shade)] back to front, "depth": L, "feet": (x, y) in
    crop px, "height": figure px, "size"}. figure = figure-depth nearer than floor-depth; props = the rest of depth.png's near pixels;
    the OTS foreground figure (when the cell has one) = leftovers nearer than the figure itself."""
    meta = json.loads((entry / "meta.json").read_text())
    if meta.get("figure_height_px", 0) <= 0:
        raise ValueError(f"{entry}: figure_height_px is 0 (figure off screen?), cannot scale")
    stale = [n for n in ("depth.png", "floor-depth.png", "figure-depth.png") if not (entry / n).exists()] + ([] if "res" in meta else ["meta res"])
    if stale:
        raise ValueError(f"{entry}: old library cell, missing {', '.join(stale)} - rebuild the library (python -m tools.greybox_library build)")
    depth, floor, fig_d = _depth(entry, "depth.png"), _depth(entry, "floor-depth.png"), _depth(entry, "figure-depth.png")
    figure = (fig_d > floor + MARGIN) & (np.abs(depth - fig_d) <= MARGIN)  # figure only where it is the nearest surface
    near = depth > floor + MARGIN
    if not (fig_d > floor + MARGIN).any():
        raise ValueError(f"{entry}: empty figure mask")
    rest = near & ~figure
    top = (fig_d[figure].max() if figure.any() else fig_d.max()) + FG_GAP
    fg = rest & (depth > top) if meta.get("foreground_figure") else np.zeros_like(rest)
    layers = [(rest & ~fg, PROPS), (figure, FIGURE), (fg, FOREGROUND)]
    ys, xs = np.nonzero(near | figure)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    h, w = depth.shape
    return {"layers": [(Image.fromarray((m[y0:y1, x0:x1] * 255).astype(np.uint8)), c) for m, c in layers if m.any()],
            "depth": Image.fromarray(np.where(near | figure, depth, 0).astype(np.uint8)[y0:y1, x0:x1]),
            "feet": (meta["feet"][0] * w - x0, meta["feet"][1] * h - y0), "height": meta["figure_height_px"]}


def _outline(mask: Image.Image) -> Image.Image:
    return ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(5)))  # 2 px band inside the edge


def _shape(mask: Image.Image, size) -> Image.Image:
    return mask.resize(size, Image.BILINEAR).point(lambda v: 255 if v > 127 else 0).filter(ImageFilter.MedianFilter(3))  # smoothing after scaling


def insert_many(plate: Path, figures: list[dict], out: Path) -> Path:
    """figures: [{entry, feet: (x, y) 0..1, height: 0..1, label, hidden_below?: 0..1, in_front?: plate-sized L mask of what
    stands in front of this figure, figure_only?: skip the cell's own props}]. Writes out plus <stem>.pose.json / .pose.png / .depth.png beside it.
    The depth patch holds each figure's own relative depth (comparable inside one figure, not between figures)."""
    out = Path(out)
    base = Image.open(plate).convert("RGB")
    W, H = base.size
    board = Image.eval(base, lambda v: int(v * DIM))
    depth = np.zeros((H, W), np.uint8)
    poses, tags = {}, []
    for f in figures:
        entry = Path(f["entry"])
        cut = cutout(entry)
        fx, fy = cut["feet"]
        s = f["height"] * H / cut["height"]
        size = (max(1, round(cut["depth"].width * s)), max(1, round(cut["depth"].height * s)))
        ox, oy = f["feet"][0] * W - fx * s, f["feet"][1] * H - fy * s
        pos = (round(ox), round(oy))
        union = Image.new("L", size, 0)
        # hidden_below: frame y (0..1) where the plate's own foreground (a counter, a rail) hides the figure
        hide = round(f["hidden_below"] * H) - pos[1] if f.get("hidden_below") is not None else None
        layers = [x for x in cut["layers"] if x[1] == FIGURE] if f.get("figure_only") else cut["layers"]
        for mask, shade in layers:
            m = _shape(mask, size)
            if hide is not None:
                m.paste(0, (0, max(0, hide), size[0], size[1]))
            if f.get("in_front") is not None:
                m = ImageChops.subtract(m, f["in_front"].crop((pos[0], pos[1], pos[0] + size[0], pos[1] + size[1])))
            board.paste(Image.new("RGB", size, shade), pos, m)
            board.paste(Image.new("RGB", size, EDGE), pos, _outline(m))
            union = ImageChops.lighter(union, m)
        canvas = Image.new("L", (W, H), 0)
        canvas.paste(cut["depth"].resize(size, Image.BILINEAR), pos, union)
        depth = np.maximum(depth, np.asarray(canvas))
        pose = json.loads((entry / "pose.json").read_text())
        meta = json.loads((entry / "meta.json").read_text())
        bw, bh = meta["res"]  # pose points are 0..1 of the whole board: move them relative to the feet, scale, re-anchor
        pts = {k: [f["feet"][0] + (v[0] - meta["feet"][0]) * bw * s / W, f["feet"][1] + (v[1] - meta["feet"][1]) * bh * s / H]
               for k, v in pose["points"].items() if v}
        label = f["label"]
        while label in poses:
            label += "'"
        poses[label] = {"points": pts, "back": pose.get("back", False)}
        ys, xs = np.nonzero(np.asarray(union))
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
