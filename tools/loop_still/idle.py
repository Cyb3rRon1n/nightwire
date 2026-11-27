"""Her idle (spec 2026-11-27-loop-idle-design.md): one displacement field over her whole cut-out, made of a breath that
rises from the hips to the shoulders, a slow weight shift over planted feet, and a small head sway about the neck.
Over the face the field is a shift plus a small-angle rotation, so the face moves only as a whole. Hair and coat tips
follow the body through damped springs (`spring`), which is linear, so the loop stays exactly periodic.

Terms have Motion's shape (cycles, phase, Px, Qx, Py, Qy): displacement = sin(a)·P − cos(a)·Q, a = 2π·c·i/N + phase."""

import numpy as np

from tools.loop_still.periodic import pick_cycles

BREATH = 0.0025     # rise, share of her height
BREATH_LAG = 0.12   # cycles the shoulders lag the belly
SHIFT = 0.004       # sideways weight shift, share of her height
SWAY = (0.5, 0.25)  # head rotation, degrees, two terms
HZ = {"breath": 0.25, "shift": 0.07, "sway": (0.15, 0.23)}
SPRING = {"hair": (0.9, 0.3), "coat": (0.6, 0.4)}  # natural frequency (Hz), damping ratio


def _ease(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def spring(c: int, seconds: float, f0: float, zeta: float) -> complex:
    """Steady-state response of a damped spring to a motion with c cycles per loop of `seconds`."""
    w, w0 = 2 * np.pi * c / seconds, 2 * np.pi * f0
    return w0 * w0 / complex(w0 * w0 - w * w, 2 * zeta * w0 * w)


def respond(term: tuple, h: complex, weight: np.ndarray) -> tuple:
    """The term plus the extra motion (h − 1)·term on a tip, scaled by the tip weight (0 at the roots): one term, so
    a spring costs nothing per frame. Maps that are None (all zero) stay None."""
    c, theta, px, qx, py, qy = term
    g = h - 1
    out = []
    for p, q in ((px, qx), (py, qy)):
        if p is None and q is None:
            out += [None, None]
            continue
        a = g * ((0 if p is None else p) - 1j * (0 if q is None else q)) * weight
        out += [((0 if p is None else p) + a.real).astype(np.float32),
                ((0 if q is None else q) - a.imag).astype(np.float32)]
    return (c, theta, *out)


def size_of(term: tuple) -> np.ndarray:
    """The largest displacement a term can give at each pixel (px)."""
    return np.sqrt(sum(m.astype(np.float64) ** 2 for m in term[2:] if m is not None) + 0).astype(np.float32)


class Idle:
    def __init__(self, matte, face, size, frames, seconds, seed, taken: set, breath: bool = True):
        self.W, self.H = W, H = size
        self.N, self.taken = frames, taken
        hard = matte >= 0.5
        self.face = face >= 0.5
        rows = np.nonzero(hard.any(axis=1))[0]
        top, bottom = (rows[0], rows[-1]) if len(rows) else (0, H - 1)
        hf = bottom - top + 1
        if self.face.any():
            fr, fc = np.nonzero(self.face.any(axis=1))[0], np.nonzero(self.face.any(axis=0))[0]
            neck, pivot_x = float(fr[-1]), (fc[0] + fc[-1]) / 2
            shoulder = neck + 0.6 * (fr[-1] - fr[0] + 1)
        else:
            cols = np.nonzero(hard.any(axis=0))[0]
            neck, pivot_x = top + 0.15 * hf, ((cols[0] + cols[-1]) / 2 if len(cols) else W / 2)
            shoulder = top + 0.22 * hf
        # a bust crop has no hips in frame: the breath still needs a real ramp below the shoulders, or the chest tears
        hip = max(min(bottom, max(top + 0.5 * hf, shoulder + 0.15 * hf)), shoulder + 2)
        self.pivot = (float(pivot_x), neck)
        y = np.arange(H, dtype=np.float32)[:, None]
        X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        s = _ease((hip - y) / (hip - shoulder)) * np.ones((1, W), np.float32)      # 0 at the hips, 1 at the shoulders
        h = _ease((bottom - y) / max(1, bottom - hip)) * np.ones((1, W), np.float32)  # 0 at the feet, 1 at the hips
        wh = _ease((shoulder - y) / max(1, shoulder - neck)) * np.ones((1, W), np.float32)  # 1 above the chin
        rng = np.random.default_rng([seed, 31])
        self.cycles: dict[str, list[int]] = {}
        self._shared, self._sway = [], []
        if breath:
            c = pick_cycles(HZ["breath"], seconds, taken)
            self.cycles["breath"] = [c]
            phi = 2 * np.pi * BREATH_LAG * s
            rise = BREATH * hf
            self._shared.append((c, 0.0, None, None, (-rise * s * np.cos(phi)).astype(np.float32),
                                 (-rise * s * np.sin(phi)).astype(np.float32)))
        c = pick_cycles(HZ["shift"], seconds, taken)
        self.cycles["shift"] = [c]
        self._shared.append((c, rng.uniform(0, 2 * np.pi), (SHIFT * hf * h).astype(np.float32), None, None, None))
        self.cycles["sway"] = []
        for deg, hz in zip(SWAY, HZ["sway"]):
            c = pick_cycles(hz, seconds, taken)
            self.cycles["sway"].append(c)
            ang = np.deg2rad(deg)
            self._sway.append((c, rng.uniform(0, 2 * np.pi), (-ang * (Y - neck)).astype(np.float32),
                               (ang * (X - pivot_x)).astype(np.float32)))
        self._wh = wh.astype(np.float32)
        self._terms: dict[bool, list] = {}
        self._hard = hard
        body = self.terms()
        self.reach = float(sum(size_of(t)[hard].max(initial=0) for t in body))

    def terms(self, hair: bool = False) -> list[tuple]:
        """The body's terms; for hair the head sway is full everywhere, since hair hangs from the head."""
        if hair not in self._terms:  # made once: the maps are big
            out = list(self._shared)
            for c, theta, rx, ry in self._sway:
                k = 1.0 if hair else self._wh
                out.append((c, theta, rx * k, None, ry * k, None))
            self._terms[hair] = out
        return self._terms[hair]

    def rigid_error(self, field: tuple[np.ndarray, np.ndarray]) -> float:
        """Largest gap (px) between the field over the face and its best-fit shift plus small rotation."""
        if not self.face.any():
            return 0.0
        ys, xs = np.nonzero(self.face)
        if len(ys) > 4000:
            k = np.linspace(0, len(ys) - 1, 4000).astype(int)
            ys, xs = ys[k], xs[k]
        dx, dy = field[0][ys, xs].astype(np.float64), field[1][ys, xs].astype(np.float64)
        x, y = xs - xs.mean(), ys - ys.mean()
        n = len(xs)
        # dx = tx − θ·y, dy = ty + θ·x
        a = np.zeros((2 * n, 3))
        a[:n, 0], a[:n, 2] = 1, -y
        a[n:, 1], a[n:, 2] = 1, x
        b = np.concatenate([dx, dy])
        sol = np.linalg.lstsq(a, b, rcond=None)[0]
        return float(np.abs(a @ sol - b).max())
