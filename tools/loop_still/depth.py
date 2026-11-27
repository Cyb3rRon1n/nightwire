"""Camera drift (spec 2026-11-27-loop-idle-design.md): a depth guess from Depth Anything V2 Small (Apache-2.0, run once
on the CPU, cached beside the still as <still>.depth.png so it can be fixed by hand) and a slow periodic sideways
drift that moves near and far things by different amounts. Focus is on her, so she and the street at her feet stay
put; her own area takes the depth around her, so what shows behind a moved edge drifts with the wall behind."""

from pathlib import Path

import cv2
import numpy as np

from tools.loop_still.periodic import pick_cycles

DEPTH_SUFFIX = ".depth.png"
AMP = (0.007, 0.003)  # drift of the farthest/nearest things, share of width, x and y
HZ = (0.05, 0.08)
CAP = 0.012           # no pixel shifts more than this share of width


def depth_path(still: Path) -> Path:
    return Path(still).with_name(Path(still).stem + DEPTH_SUFFIX)


def load_or_make_depth(still: Path, model: Path, redo: bool = False) -> np.ndarray | None:
    """Relative disparity 0..1 (1 = nearest) at the still's size, or None when there is no cache and no model."""
    still, cached = Path(still), depth_path(still)
    img = cv2.imread(str(still))
    if img is None:
        raise FileNotFoundError(still)
    if cached.exists() and not redo:
        d = cv2.imread(str(cached), cv2.IMREAD_UNCHANGED).astype(np.float32)
        d = d / (65535 if d.max() > 255 else 255)
        return cv2.resize(d, img.shape[1::-1], interpolation=cv2.INTER_LINEAR)
    if not Path(model).exists():
        return None
    from PIL import Image  # late: only when a depth map is made
    from transformers import pipeline
    pipe = pipeline("depth-estimation", model=str(model), device="cpu")
    d = np.asarray(pipe(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))["predicted_depth"].squeeze(),
                   np.float32)
    d = cv2.resize(d, img.shape[1::-1], interpolation=cv2.INTER_CUBIC)
    d = (d - d.min()) / (np.ptp(d) or 1)
    cv2.imwrite(str(cached), (d * 65535).round().astype(np.uint16))
    return d


class Drift:
    def __init__(self, disp, matte, size, frames, seconds, taken: set, seed: int = 1):
        self.W, self.H = W, H = size
        self.N = frames
        d = cv2.resize(disp.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
        her = cv2.resize(matte.astype(np.float32), (W, H)) >= 0.5
        self.focus = float(np.median(d[her])) if her.any() else float(np.median(d))
        if her.any():  # fill her with the depth around her, at quarter size (Telea on a big hole is slow)
            grow = cv2.dilate(her.astype(np.uint8), np.ones((5, 5), np.uint8))
            sw, sh = max(1, W // 4), max(1, H // 4)
            small = cv2.resize((d * 65535).astype(np.uint16), (sw, sh), interpolation=cv2.INTER_AREA)
            hole = cv2.dilate(cv2.resize(grow, (sw, sh), interpolation=cv2.INTER_NEAREST), np.ones((3, 3), np.uint8))
            filled = cv2.inpaint(small, hole, 5, cv2.INPAINT_TELEA).astype(np.float32) / 65535
            d = np.where(grow > 0, cv2.resize(filled, (W, H), interpolation=cv2.INTER_LINEAR), d)
        d = cv2.GaussianBlur(d, (0, 0), max(0.5, 0.004 * W))  # depth edges stretch a little instead of tearing
        self.rel = (d - self.focus).astype(np.float32)
        rng = np.random.default_rng([seed, 41])
        self.terms = [(pick_cycles(hz, seconds, taken), rng.uniform(0, 2 * np.pi), a * W) for hz, a in zip(HZ, AMP)]
        self.cap = CAP * W
        near = cv2.dilate(her.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0 if her.any() else np.ones_like(her)
        self.reach = float(min(self.cap, np.abs(self.rel[near]).max() * np.hypot(AMP[0], AMP[1]) * W))
        self._grid = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))

    def offset(self, i: int) -> tuple[float, float]:
        return tuple(a * np.sin(2 * np.pi * c * i / self.N + t) for c, t, a in self.terms)

    def shift(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        ox, oy = self.offset(i)
        return (np.clip(self.rel * np.float32(ox), -self.cap, self.cap),
                np.clip(self.rel * np.float32(oy), -self.cap, self.cap))

    def apply(self, img: np.ndarray, i: int) -> np.ndarray:
        dx, dy = self.shift(i)
        gx, gy = self._grid
        return cv2.remap(img, gx - dx, gy - dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
