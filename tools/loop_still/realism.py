"""Realism layers for a loop (spec 2026-11-26-loop-realism-design.md): raindrops rippling the wet street, neon bloom,
rain lit by the lights it falls through, and film grain. All periodic in the frame index except grain, which is
fresh each frame (seeded by frame number) so it never loops visibly."""

import cv2
import numpy as np

DROPS = {"none": 0, "drizzle": 60, "steady": 160, "heavy": 320}  # ripple drops per loop per 1920 px of width
_LIFE_S = 0.8
_SQUASH = 0.35       # the street is seen at a grazing angle, so a ring is a flat ellipse
_PUSH = 10.0         # px the street is pushed by a full-height ripple slope, at the bottom of the frame
_RING_LIGHT = 0.25
RAIN_TINT = np.array([1.0, 0.95, 0.8], np.float32)  # cool blue-white, BGR (as in render)


class Ripples:
    """Rain landing on the street as ring waves. Each drop lives 0.8 s and is active at frames (t0 + age) % N, so
    the field repeats exactly every N frames and no frame near the seam is emptier than any other. Only the street
    rows are worked on; offsets are clamped to _PUSH px and kept _PUSH + 2 px clear of her, so a ripple never pulls
    her pixels into the street (`leak` measures it every frame)."""

    def __init__(self, size, frames, fps, ground, seed, preset, avoid=None):
        self.W, self.H = W, H = size
        self.N = frames
        self.w2, self.h2 = max(1, W // 2), max(1, H // 2)
        top = int(round(ground * H))
        area = np.zeros((H, W), np.float32)
        if top < H:
            y = (np.arange(H, dtype=np.float32) - top) / max(1, H - top)
            area[top:] = np.clip(y[top:, None] * 8, 0, 1)            # ease in over the first eighth below the line
            area[top] = 0
        margin = int(np.ceil(_PUSH)) + 2
        her = (avoid >= 0.5) if avoid is not None else np.zeros((H, W), bool)
        if her.any():
            area[cv2.dilate(her.astype(np.uint8), np.ones((2 * margin + 1,) * 2, np.uint8)) > 0] = 0
        self.area = area
        self.y0 = max(0, (top - margin) // 2 * 2)                     # even, so it maps onto the half-size grid
        rows = H - self.y0
        persp = np.zeros(H, np.float32)
        if top < H:
            persp[top:] = 0.3 + 0.7 * (np.arange(H - top, dtype=np.float32) / max(1, H - top - 1))
        self.k_push = (_PUSH * persp[:, None] * area)[self.y0:]
        self.her = her[self.y0:].astype(np.float32)
        self.has_her = bool(her.any())
        self.gx, self.gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(rows, dtype=np.float32))
        self.leak = 0.0

        rng = np.random.default_rng([seed, 17])
        n = round(DROPS[preset] * W / 1920)
        half = cv2.resize(area, (self.w2, self.h2), interpolation=cv2.INTER_AREA)
        ys, xs = np.nonzero(half > 0.5)
        self.empty = n == 0 or len(ys) == 0
        self.life = max(2, round(_LIFE_S * fps))
        sc = self.h2 / 669
        self.speed = 40 * sc / self.life                          # ring reaches ~40 px (half size) by the end
        self.width, self.k = 3 * sc + 1, 2 * np.pi / (6 * sc + 2)
        self.R = int(np.ceil(self.speed * self.life + 3 * self.width))
        yy, xx = np.mgrid[-self.R:self.R + 1, -self.R:self.R + 1].astype(np.float32)
        self.r = np.hypot(xx, yy / _SQUASH)
        if self.empty:
            self.drops = np.zeros((0, 3), int)
            return
        pick = rng.integers(0, len(ys), n)
        self.drops = np.stack([xs[pick], ys[pick], rng.integers(0, frames, n)], 1)

    def height(self, i: int) -> np.ndarray:
        h = np.zeros((self.h2, self.w2), np.float32)
        R, r = self.R, self.r
        for x, y, t0 in self.drops:
            age = (i - t0) % self.N
            if age >= self.life:
                continue
            front = self.speed * age
            fade = (1 - age / self.life) ** 2
            patch = np.exp(-((r - front) / self.width) ** 2) * np.sin(self.k * (r - front)) * fade
            x0, x1, y0, y1 = x - R, x + R + 1, y - R, y + R + 1
            cx0, cy0 = max(0, -x0), max(0, -y0)
            cx1, cy1 = patch.shape[1] - max(0, x1 - self.w2), patch.shape[0] - max(0, y1 - self.h2)
            h[max(0, y0):min(self.h2, y1), max(0, x0):min(self.w2, x1)] += patch[cy0:cy1, cx0:cx1]
        return h

    def offsets(self, i: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(dx, dy, ring height) for the street rows (from y0 down), zero outside the street area."""
        h = self.height(i)[self.y0 // 2:]
        gy, gx = np.gradient(h)
        size = (self.W, self.H - self.y0)
        dx = np.clip(cv2.resize(gx, size, interpolation=cv2.INTER_LINEAR) * self.k_push, -_PUSH, _PUSH)
        dy = np.clip(cv2.resize(gy, size, interpolation=cv2.INTER_LINEAR) * self.k_push, -_PUSH, _PUSH)
        return dx, dy, cv2.resize(h, size, interpolation=cv2.INTER_LINEAR) * self.area[self.y0:]

    def apply(self, img: np.ndarray, i: int, extra: np.ndarray | None = None, ripple: bool = True) -> np.ndarray:
        """The street resampled through the ripples, with a faint lit ring where the street is bright. `extra` (the
        mirror) is drawn through the same ripples and added inside the street area; ripple=False adds it flat."""
        if self.empty or not ripple:
            return img if extra is None else img + extra * self.area[..., None]
        y0 = self.y0
        dx, dy, h = self.offsets(i)
        mx, my = self.gx + dx, self.gy + dy
        st = img[y0:]
        moved = cv2.remap(st, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        if extra is not None:
            moved = moved + cv2.remap(extra[y0:], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        a = self.area[y0:, :, None]
        if self.has_her:
            src = cv2.remap(self.her, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            self.leak = float((src * (a[..., 0] > 0)).max())
        sh = st.shape[1::-1]
        lit = cv2.resize(cv2.GaussianBlur(cv2.resize(st, (sh[0] // 2 or 1, sh[1] // 2 or 1),
                                                     interpolation=cv2.INTER_AREA), (0, 0), 2), sh)
        moved = moved + _RING_LIGHT * np.clip(h, 0, None)[..., None] * lit
        out = img.copy()
        out[y0:] = np.where(a > 0, st * (1 - a) + moved * a, st)
        return out


def _soft(x, lo, hi):
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


class Bloom:
    """Neon glow in wet air: bright, saturated pixels blurred at three sizes and screen-added; the widest is warm
    (halation). The mask comes from the base plate once; the glow follows whatever the lights do each frame."""

    WARM = np.array([0.7, 0.85, 1.15], np.float32)  # BGR

    def __init__(self, base: np.ndarray, strength: float = 0.22, avoid: np.ndarray | None = None):
        hi, lo = base.max(2), base.min(2)
        sat = (hi - lo) / np.maximum(hi, 1e-6)
        mask = _soft(hi, 0.5, 0.7) * _soft(sat, 0.25, 0.4)
        if avoid is not None:  # her own bright clothes are not a light
            mask *= cv2.dilate((avoid >= 0.5).astype(np.uint8), np.ones((5, 5), np.uint8)) == 0
        self.mask = mask[..., None].astype(np.float32)
        self.strength = strength
        self.H, self.W = base.shape[:2]
        self.small = (max(1, self.W // 4), max(1, self.H // 4))
        self.mask_small = cv2.resize(self.mask, self.small, interpolation=cv2.INTER_AREA)[..., None]
        self.sig = [s * self.W / 1920 / 4 for s in (6, 24, 80)]

    def apply(self, img: np.ndarray) -> np.ndarray:
        if not self.mask.any():
            return img
        b = cv2.resize(img, self.small, interpolation=cv2.INTER_AREA) * self.mask_small
        g = 1.0 * cv2.GaussianBlur(b, (0, 0), max(0.5, self.sig[0])) \
            + 0.8 * cv2.GaussianBlur(b, (0, 0), max(0.5, self.sig[1])) \
            + 0.6 * cv2.GaussianBlur(b, (0, 0), max(0.5, self.sig[2])) * self.WARM
        g = np.clip(self.strength * cv2.resize(g, (self.W, self.H), interpolation=cv2.INTER_LINEAR), 0, 1)
        return 1 - (1 - img) * (1 - g)


def light_map(img: np.ndarray) -> np.ndarray:
    """The light around each point: the image blurred at 1/8 size."""
    H, W = img.shape[:2]
    small = cv2.resize(img, (max(1, W // 8), max(1, H // 8)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 4)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)


def rain_tint(lmap: np.ndarray) -> np.ndarray:
    """Rain glints and takes colour near lights and nearly vanishes in the dark."""
    return np.clip(0.35 * RAIN_TINT + 1.6 * lmap, 0, 1.6)


def grain(shape, seed: int, i: int, amount: float = 0.012) -> np.ndarray:
    H, W = shape
    return np.random.default_rng([seed, 13, i]).standard_normal((H, W, 1), dtype=np.float32) * amount
