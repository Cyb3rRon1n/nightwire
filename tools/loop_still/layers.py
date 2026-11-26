"""City layers for a loop: far and near rain, street splashes and fog, each a pure function of the frame index with
whole cycles per loop (spec "Design", steps 2 and 4; Clip Studio tip 7699: far rain thin and faint, near rain
sparse and longer, splashes over about 3 frames)."""

import cv2
import numpy as np

from tools.loop_still.periodic import divisors_between, tile_noise

RAIN = {"none": 0, "drizzle": 250, "steady": 600, "heavy": 1200}  # far drops per 1920 px of width
_NEAR_SHARE = 0.12
_SPLASH = ((1.0, 0.5), (2.0, 0.35), (3.0, 0.18))  # (radius scale, alpha) over a splash's 3 frames


class Rain:
    """Streaks that each fall a whole number of screen heights per loop, so frame N is frame 0."""

    def __init__(self, size, frames, preset, seed, slant=0.12, near=False):
        self.W, self.H = size
        self.N, self.slant, self.near = frames, slant, near
        rng = np.random.default_rng([seed, int(near)])
        sc = self.H / 1338
        n = round(RAIN[preset] * self.W / 1920 * (_NEAR_SHARE if near else 1))
        laps = rng.integers(10, 15, n) if near else rng.integers(5, 10, n)
        depth = rng.random(n)
        self.length = ((30 + 30 * depth) if near else (8 + 22 * (laps - 5) / 4)) * sc
        self.alpha = (0.25 + 0.15 * depth) if near else (0.10 + 0.12 * (laps - 5) / 4)
        self.width = 2 if near else 1
        self.margin = float(self.length.max()) + 40 if n else 40.0
        self.laps = laps
        self.x0 = rng.uniform(0, self.W + self.H * slant + self.margin, n)
        self.y0 = rng.uniform(0, self.H + self.margin, n)

    def layer(self, i: int) -> np.ndarray:
        out = np.zeros((self.H, self.W), np.float32)
        if not len(self.x0):
            return out
        t = (i % self.N) / self.N
        span = self.H + self.margin
        ys = (self.y0 + self.laps * span * t) % span - self.margin / 2
        xs = self.x0 - ys * self.slant
        for x, y, ln, a in zip(xs, ys, self.length, self.alpha):
            cv2.line(out, (int(x), int(y)), (int(x + ln * self.slant), int(y + ln)), float(a), self.width, cv2.LINE_AA)
        return out


class Splashes:
    """Small rings on the street: each site splashes once per period (a divisor of the loop), over 3 frames, at a
    spot that moves each time."""

    def __init__(self, size, frames, ground, seed, count, avoid=None):
        self.W, self.H = size
        self.N, self.seed = frames, seed
        rng = np.random.default_rng([seed, 7])
        options = divisors_between(frames, 6, 48)
        self.periods = [int(rng.choice(options)) for _ in range(count)]
        self.phase = [int(rng.integers(0, p)) for p in self.periods]
        self.top = int(ground * self.H)
        self.r = max(2.0, 3 * self.H / 1338)
        free = np.ones((self.H, self.W), bool)
        if avoid is not None:
            free &= cv2.dilate((avoid >= 0.5).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
        free[: self.top] = False
        ys, xs = np.nonzero(free)
        self.spots = []  # per site, one spot per occurrence in the loop
        for p in self.periods:
            k = self.N // p
            pick = rng.integers(0, len(ys), k) if len(ys) else np.zeros(0, int)
            self.spots.append([(int(xs[j]), int(ys[j])) for j in pick])

    def layer(self, i: int) -> np.ndarray:
        out = np.zeros((self.H, self.W), np.float32)
        for p, ph, spots in zip(self.periods, self.phase, self.spots):
            if not spots:
                continue
            j = (i + ph) % self.N
            f = j % p
            if f < len(_SPLASH):
                x, y = spots[j // p]
                scale, a = _SPLASH[f]
                r = self.r * scale
                cv2.ellipse(out, (x, y), (max(1, int(r * 2)), max(1, int(r * 0.6))), 0, 0, 360, a, 1, cv2.LINE_AA)
        return out


class Fog:
    """Wrapping noise that drifts sideways by exactly one tile per loop."""

    def __init__(self, size, frames, seed, strength=0.08):
        self.W, self.H = size
        self.N = frames
        self.tile = strength * tile_noise(self.H, self.W, max(8, self.W // 6), np.random.default_rng([seed, 11])) ** 1.5

    def layer(self, i: int) -> np.ndarray:
        return np.roll(self.tile, int(round(self.W * (i % self.N) / self.N)), axis=1)
