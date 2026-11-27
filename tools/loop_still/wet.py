"""Wet light on her (spec 2026-11-27-loop-idle-design.md): the lights' changes wash over her (half strength on the
face), her own painted highlights glint when light grows, and drops form at the lowest hair and coat tips and fall.
All periodic: the wash and glints follow the periodic lights, the drips run on a wrapped schedule."""

import cv2
import numpy as np

WASH = 0.3
DRIP_EVERY_S = 2.5
SWELL_S, FALL_S = 0.5, 0.35
GRAVITY = 3000.0    # px/s² at 1338 px high


def spread(delta: np.ndarray) -> np.ndarray:
    """The lights' change this frame (city − plate, signed) spread out by 2% of the width, as light falls on her."""
    H, W = delta.shape[:2]
    small = cv2.resize(delta, (max(1, W // 4), max(1, H // 4)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, 0.02 * W / 4))
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)


def wash(light: np.ndarray, alpha: np.ndarray, face: np.ndarray, k: float = WASH) -> np.ndarray:
    """What the spread light change (`spread`) adds over her: alpha is her cut-out as drawn now, face her face as
    drawn now (it gets half)."""
    w = (alpha * (1 - 0.5 * np.clip(face, 0, 1))).astype(np.float32)
    return k * w[..., None] * light


class Sheen:
    """Her painted highlights (luma above its local mean), away from the face, as a mask that glints with light."""

    def __init__(self, still: np.ndarray, matte: np.ndarray, face: np.ndarray):
        H, W = still.shape[:2]
        sc = H / 1338
        luma = cv2.cvtColor(still.astype(np.float32), cv2.COLOR_BGR2GRAY)
        hp = luma - cv2.GaussianBlur(luma, (0, 0), max(1.0, 4 * sc))
        away = cv2.dilate((face >= 0.5).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
        self.mask = (np.clip((hp - 0.02) * 5, 0, 1) * (matte >= 0.5) * away).astype(np.float32)

    def glint(self, mask: np.ndarray, lmap: np.ndarray, gain: np.ndarray) -> np.ndarray:
        """mask: the sheen as drawn now; lmap: the light around each point; gain: the light's growth (blurred
        city − plate, positive part)."""
        return mask[..., None] * (0.05 * lmap + 0.8 * np.clip(gain, 0, None))


def _tips(mask: np.ndarray, avoid: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """The lowest points of a mask's lower edge (local maxima of each column's lowest row), at least gap px apart."""
    m = mask >= 0.5
    if not m.any():
        return []
    H = m.shape[0]
    low = np.where(m.any(axis=0), H - 1 - np.argmax(m[::-1], axis=0), -1)
    half = max(2, gap // 2)
    pts = []
    for x in np.argsort(-low, kind="stable"):
        y = low[x]
        if y < 0 or avoid[y, x]:
            continue
        if y < low[max(0, x - half):x + half + 1].max():
            continue
        if all(abs(x - px) >= gap for px, _ in pts):
            pts.append((int(x), int(y)))
    return pts


class Drips:
    def __init__(self, regions: dict, face: np.ndarray, size, frames: int, fps: int, seed: int, ground: float):
        self.W, self.H = W, H = size
        self.N, self.fps = frames, fps
        self.sc = H / 1338
        self.ground = int(round(ground * H))
        avoid = cv2.dilate((face >= 0.5).astype(np.uint8), np.ones((41, 41), np.uint8)) > 0
        self.face = face >= 0.5
        cands = [(name, x, y) for name, m in sorted(regions.items()) for x, y in _tips(m, avoid, max(6, W // 60))]
        self.swell, self.fall = max(2, round(SWELL_S * fps)), max(2, round(FALL_S * fps))
        n = round(frames / fps / DRIP_EVERY_S) if cands else 0
        rng = np.random.default_rng([seed, 53])
        self.drops = [(*cands[k], int(t)) for k, t in zip(rng.integers(0, len(cands), n), rng.integers(0, frames, n))] \
            if n else []
        self.r = max(1.0, 2.2 * self.sc)

    def layer(self, i: int, offsets: dict | None = None) -> np.ndarray:
        """0..1 bead brightness at frame i; offsets: {region: (dx, dy)} so a tip moves with its layer."""
        out = np.zeros((self.H, self.W), np.float32)
        for name, x, y, t0 in self.drops:
            age = (i - t0) % self.N
            if age >= self.swell + self.fall:
                continue
            if offsets and name in offsets:
                dx, dy = offsets[name]
                x, y = x + float(dx[y, x]), y + float(dy[y, x])
            if age < self.swell:
                r = self.r * np.sqrt((age + 1) / self.swell)
                cy, stretch = y + 0.6 * r, 1.0
            else:
                t = (age - self.swell + 1) / self.fps
                r = self.r
                cy = y + r + 0.5 * GRAVITY * self.sc * t * t
                stretch = 1 + GRAVITY * self.sc * t / self.fps / (2 * r)  # a little motion blur along the fall
                if cy > self.ground:
                    continue
            self._bead(out, x, cy, r, stretch)
        out[self.face] = 0
        return out

    def _bead(self, out, x, y, r, stretch):
        R = int(np.ceil(3 * r * stretch)) + 1
        x0, x1 = max(0, int(x) - R), min(self.W, int(x) + R + 1)
        y0, y1 = max(0, int(y) - R), min(self.H, int(y) + R + 1)
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        b = np.exp(-(((xx - x) / r) ** 2 + ((yy - y) / (r * stretch)) ** 2)) * 0.7 / np.sqrt(stretch)
        out[y0:y1, x0:x1] = np.maximum(out[y0:y1, x0:x1], b)
