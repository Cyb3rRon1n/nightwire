"""Subtle blinks (owner 2026-11-26: "blinks are fine, keep it subtle"): drawn half-closed and closed eye patches are
swapped in, never warped (spec "Blinks"). Timing from Bloop Animation (2 frames closing, 1 closed, 3 opening at 24
fps; fast 5, slow 9); gaps 3-8 s, uneven, from the seed (Wikipedia "Blinking": about 17 a minute, 2-10 s apart)."""

from pathlib import Path

import cv2
import numpy as np

SHAPES = {
    "regular": ["half", "closed", "closed", "half", "half"],
    "fast": ["half", "closed", "half", "half"],
    "slow": ["half", "half", "closed", "closed", "half", "half", "half"],
}
_EDGE_S = 0.5            # no blink in the first or last half second, so none straddles the seam
_GAP_S = (3.0, 8.0)
_DOUBLE_AFTER = 6        # frames between the two blinks of a double blink


def _shape(names: list[str], fps: int) -> list[str]:
    n = max(len(names), round(len(names) * fps / 24))
    return [names[int(k * len(names) / n)] for k in range(n)]


def schedule(frames: int, fps: int, seed: int) -> list[tuple[int, list[str]]]:
    """(start frame, patch name per frame) for each blink in the loop. The gap across the seam is kept in range too,
    so the repeat point can't be told by a long or short pause."""
    edge, lo, hi = round(_EDGE_S * fps), _GAP_S[0] * fps, _GAP_S[1] * fps
    rng = np.random.default_rng([seed, 3])
    best: list[tuple[int, list[str]]] = []
    for _ in range(200):
        out: list[tuple[int, list[str]]] = []
        s = int(rng.integers(edge, edge + 5 * fps + 1))
        while True:
            roll = rng.random()
            kind = "fast" if roll < 0.1 else "slow" if roll < 0.2 else "regular"
            group = [(s, _shape(SHAPES[kind], fps))]
            if rng.random() < 1 / 6:
                second = s + len(group[0][1]) + _DOUBLE_AFTER
                group.append((second, _shape(SHAPES["regular"], fps)))
            if group[-1][0] + len(group[-1][1]) > frames - edge:
                break
            out += group
            s += int(round(rng.uniform(lo, hi)))
        if not out:
            continue
        wrap = frames - out[-1][0] + out[0][0]
        if lo <= wrap <= hi:
            return out
        best = best or out
    return best


class Blinks:
    def __init__(self, half: np.ndarray, closed: np.ndarray, frames: int, fps: int, seed: int):
        self.patches = {"half": half.astype(np.float32), "closed": closed.astype(np.float32)}
        for k, p in self.patches.items():
            if p.max() > 1:
                self.patches[k] = p / 255
        self.mask = np.maximum(self.patches["half"][..., 3], self.patches["closed"][..., 3])
        self.schedule = schedule(frames, fps, seed)
        self.N = frames
        self._at = {start + k: name for start, names in self.schedule for k, name in enumerate(names)}

    def apply(self, img: np.ndarray, i: int) -> np.ndarray:
        name = self._at.get(i % self.N)
        if name is None:
            return img
        p = self.patches[name]
        a = p[..., 3:4]
        return img * (1 - a) + p[..., :3] * a


def load_blinks(still: Path, frames: int, fps: int, seed: int, fit=None) -> Blinks | None:
    """Blinks from <still>.blink-half.png and <still>.blink-closed.png (RGBA, the still's size), or None unless both
    exist. `fit` maps a still-sized image to the output size the same way the still is mapped."""
    still = Path(still)
    paths = [still.with_name(f"{still.stem}.blink-{n}.png") for n in ("half", "closed")]
    if not all(p.exists() for p in paths):
        return None
    size = cv2.imread(str(still)).shape[1::-1]
    pats = []
    for p in paths:
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if im.ndim != 3 or im.shape[2] != 4:
            raise ValueError(f"{p} needs an alpha channel that marks the eye area")
        if im.shape[1::-1] != size:  # line it up with the still first, as the masks are
            im = cv2.resize(im, size, interpolation=cv2.INTER_LINEAR)
        pats.append(fit(im) if fit else im)
    return Blinks(pats[0], pats[1], frames, fps, seed)
