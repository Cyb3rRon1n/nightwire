"""What a plate's camera saw: its eye-level line (horizon), camera height and a depth map, so grey figures stand at the
right size and go behind what is in front of them. Saved beside the plate as <stem>.camera.json and <stem>.depth.png.

Height rule (single-view metrology): on flat ground, a point at frame row y is (y - horizon) * H / cam_m pixels per metre,
so a figure of real height h metres whose feet touch that row is h * (y - horizon) * H / cam_m pixels tall."""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CAM_M = 1.5          # default camera height: a standing operator
MANNEQUIN_M = 1.70   # the library mannequin's standing height, as its eye-level cells measure it
DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"  # Apache-2.0, CPU, ~1 s per plate
NEAR = 12            # depth levels (of 255) nearer than the feet that count as "in front of the figure"


def camera_path(plate: Path) -> Path:
    return plate.with_name(plate.stem + ".camera.json")


def depth_path(plate: Path) -> Path:
    return plate.with_name(plate.stem + ".depth.png")


def horizon_from_lines(png: Path) -> tuple[float | None, float]:
    """Horizon row (0..1, may be outside the frame) from the vanishing point most receding lines agree on, and a score
    (summed length of agreeing lines / frame width). None when the plate has too few receding lines (dark or flat)."""
    import cv2
    g = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    H, W = g.shape
    segs = cv2.createLineSegmentDetector().detect(cv2.createCLAHE(3.0).apply(g))[0]
    lines = []
    for x1, y1, x2, y2 in ([] if segs is None else segs.reshape(-1, 4)):   # (N,1,4) or (N,4) depending on the OpenCV build
        n = np.hypot(x2 - x1, y2 - y1)
        a = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
        if n > 0.04 * W and (8 < a < 80 or 100 < a < 172):  # receding: neither level nor upright
            lines.append((np.cross([x1, y1, 1.0], [x2, y2, 1.0]), np.array([(x1 + x2) / 2, (y1 + y2) / 2]), np.array([x2 - x1, y2 - y1]), n))
    if len(lines) < 4:
        return None, 0.0
    rng, best = np.random.default_rng(0), (0.0, None)
    cos2 = np.cos(np.radians(2))
    for _ in range(3000):  # ponytail: RANSAC over pairs, O(3000 * lines); fine for one plate at a time
        i, j = rng.choice(len(lines), 2, replace=False)
        p = np.cross(lines[i][0], lines[j][0])
        if abs(p[2]) < 1e-9:
            continue
        p = p[:2] / p[2]
        if not (-2 * W < p[0] < 3 * W and -H < p[1] < 2 * H):
            continue
        score = 0.0
        for _, mid, d, n in lines:
            v = p - mid
            if abs(d @ v) / (np.linalg.norm(d) * np.linalg.norm(v) + 1e-9) > cos2:
                score += n
        if score > best[0]:
            best = (score, p)
    if best[1] is None or best[0] < 0.5 * W:
        return None, best[0] / W
    return float(best[1][1] / H), best[0] / W


def depth_map(png: Path) -> Image.Image:
    """Relative depth, white = near (Depth Anything V2 Small)."""
    from transformers import pipeline
    d = pipeline("depth-estimation", model=DEPTH_MODEL, device="cpu")(Image.open(png).convert("RGB"))["depth"]
    return d.convert("L").resize(Image.open(png).size, Image.BILINEAR)


def analyse(plate: Path, redo: bool = False) -> dict:
    """Writes <stem>.camera.json and <stem>.depth.png. A camera file set by hand (source != "auto") is kept."""
    cam_file = camera_path(plate)
    cam = json.loads(cam_file.read_text()) if cam_file.exists() else {}
    if not depth_path(plate).exists() or redo:
        depth_map(plate).save(depth_path(plate))
    if cam.get("source", "auto") == "auto":
        y, score = horizon_from_lines(plate)
        cam = {"horizon_y": None if y is None else round(y, 3), "cam_height_m": cam.get("cam_height_m", CAM_M),
               "source": "auto", "line_score": round(score, 2)}
        cam_file.write_text(json.dumps(cam, indent=1))
    return cam


def set_camera(plate: Path, horizon_y: float, cam_height_m: float | None = None, who: str = "owner") -> dict:
    cam_file = camera_path(plate)
    cam = json.loads(cam_file.read_text()) if cam_file.exists() else {"cam_height_m": CAM_M}
    cam.update(horizon_y=round(horizon_y, 3), source=who)
    if cam_height_m is not None:
        cam["cam_height_m"] = cam_height_m
    cam_file.write_text(json.dumps(cam, indent=1))
    return cam


def load(plate: Path) -> dict | None:
    f = camera_path(plate)
    cam = json.loads(f.read_text()) if f.exists() else None
    return cam if cam and cam.get("horizon_y") is not None else None


def pose_height_m(meta: dict) -> float:
    """Apparent height (m) of a library cell's figure in its pose, measured with the cell's own camera: a seated pose is
    shorter, and a high camera foreshortens. Correct on a plate whose camera pitch is close to the cell's."""
    H = meta["res"][1]
    px_per_m = (meta["feet"][1] - meta["horizon_y"]) * H / meta["camera"]["height"]
    return meta["figure_height_px"] / px_per_m


def figure_height(feet_y: float, cam: dict, pose_m: float, person_cm: int) -> float:
    """Figure height as a fraction of the plate's frame height. Raises when the feet are above the horizon."""
    gap = feet_y - cam["horizon_y"]
    if gap <= 0.01:
        raise ValueError(f"feet at y={feet_y:.2f} are on or above the horizon (y={cam['horizon_y']:.2f}): not on the floor")
    return pose_m * (person_cm / 100 / MANNEQUIN_M) * gap / cam["cam_height_m"]


def in_front_mask(depth: Image.Image, feet: tuple[float, float]) -> Image.Image:
    """Plate pixels nearer than the floor under the figure's feet (counters, rails, chairs in front of it), as an L mask.
    ponytail: one reference depth at the feet; feet hidden behind a counter read the counter, so keep hidden_below there."""
    d = np.asarray(depth, dtype=np.int16)
    h, w = d.shape
    x, y = min(w - 1, max(0, round(feet[0] * w))), min(h - 1, max(0, round(feet[1] * h) - 2))
    ref = int(np.median(d[max(0, y - 3):y + 1, max(0, x - 3):x + 4]))
    return Image.fromarray(((d > ref + NEAR) * 255).astype(np.uint8))


def check_image(plate: Path, out: Path, person_cm: int = 165) -> Path:
    """The plate with its horizon (red) and a person-height ruler (yellow) standing at three floor points, to judge by eye."""
    cam = load(plate)
    im = Image.open(plate).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    if cam is None:
        d.text((20, 20), "no horizon found: set it with  shorts camera <short> <plate> --horizon Y", fill=(255, 80, 80))
    else:
        hy = cam["horizon_y"] * H
        d.line((0, hy, W, hy), fill=(255, 60, 60), width=3)
        for fx, fy in ((0.25, 0.92), (0.5, 0.8), (0.75, 0.92)):
            if fy > cam["horizon_y"] + 0.02:
                h = figure_height(fy, cam, MANNEQUIN_M, person_cm) * H
                x, y = fx * W, fy * H
                d.line((x, y, x, y - h), fill=(255, 220, 0), width=5)
                d.text((x + 6, y - h), f"{person_cm} cm", fill=(255, 220, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
