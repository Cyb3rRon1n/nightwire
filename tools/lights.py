"""Animate only the lights of a still: the image never moves, each light just breathes or flickers.

    python -m tools.lights STILL.png OUT.mp4 [--size 3840x2160] [--seconds 60] [--exclude MASK.png]
                     [--train POLY --floor POLY --passes 9,-31,47]

Light blobs = bright + saturated pixels (neon, signs, windows). Big window fields are split into small cells so
each window group twinkles on its own; neon signs breathe whole; a few tubes flicker now and then.
Each light's brightness is a sum of 3 sines with random whole-number cycle counts over the loop, so rhythms are
irregular but the loop is seamless. With ~1000+ independent lights the repeat point cannot be spotted.

--train: polygon (fractions of width/height, "x,y;x,y;...") of the glass a train passes behind. One full train
(enters, passes, leaves) at each --passes time in seconds; a negative time runs right-to-left. Keep passes clear
of the loop end so the loop join never falls mid-train. --floor polygon brightens while a train passes.
--sweeps: a passing car's headlights sweep across the room at each time (s); --blink POLY: that sign blinks twice
after each sweep. The picture itself never moves.
EXCLUDE mask: white = never touch (e.g. a character), resized to the output.
"""
import argparse
import subprocess

import cv2
import numpy as np
from scipy import ndimage


def cover(im, w, h):
    s = max(w / im.shape[1], h / im.shape[0])
    im = cv2.resize(im, (round(im.shape[1] * s), round(im.shape[0] * s)), interpolation=cv2.INTER_LANCZOS4)
    l, t = (im.shape[1] - w) // 2, (im.shape[0] - h) // 2
    return im[t:t + h, l:l + w]


class Lights:
    """Light blobs found in a still (BGR uint8 array), breathing over a seamless loop of `seconds`.
    gain(i) -> (H, W, 1) multiplier for frame i; frame(i) adds the optional train and headlight-sweep effects."""

    def __init__(self, still, size="1920x1080", seconds=60, fps=24, seed=1, strength=0.3, exclude=None,
                 train=None, floor=None, passes="", sweeps="", blink=None):
        W, H = map(int, size.split("x"))
        self.W, self.H = W, H
        self.fps, self.strength = fps, strength
        rng = np.random.default_rng(seed)
        self.img = img = cover(still, W, H).astype(np.float32) / 255
        sc = self.sc = W / 1920                                     # thresholds were tuned at 1080p
        hsv = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
        light = (hsv[..., 2] > 150) & (hsv[..., 1] > 60) | (hsv[..., 2] > 225)
        if exclude is not None:
            light &= ~(cover(exclude, W, H) > 127)
        light = ndimage.binary_opening(light, iterations=max(1, round(sc)))
        self.light = light
        comp, nc = ndimage.label(light)
        area = ndimage.sum(light, comp, range(nc + 1)); sat = ndimage.mean(hsv[..., 1], comp, range(nc + 1))
        big = (area > 2500 * sc * sc) & (sat < 150); big[0] = False
        self.c = c = max(1, round(14 * sc))
        cell = (np.arange(H)[:, None] // c) * (W // c + 1) + (np.arange(W)[None, :] // c)
        labels = np.where(big[comp], nc + 1 + cell, comp); labels[~light] = 0
        _, labels = np.unique(labels, return_inverse=True); labels = labels.reshape(H, W).astype(np.int32)
        self.n = n = int(labels.max())
        self.labels = ndimage.grey_dilation(labels, size=max(1, round(5 * sc)))
        self.weight = cv2.GaussianBlur(light.astype(np.float32), (0, 0), 3 * sc)

        self.N = N = max(1, round(seconds * fps))
        self.seconds = seconds
        self.J = 3                                             # sines per light; cycle counts = whole numbers per loop
        self.k = rng.integers(1, max(2, round(seconds / 2.5)), (self.J, n + 1))   # periods from ~2.5 s to the full loop
        self.ph = rng.random((self.J, n + 1))
        self.amp = rng.uniform(0.15, 0.6, (self.J, n + 1)) * rng.uniform(0.3, 1.0, n + 1)
        self.amp[:, 0] = 0
        nflick = rng.poisson(seconds / 40, n + 1) * (rng.random(n + 1) < 0.15); nflick[0] = 0   # rare failing tubes
        self.fl = [(i, f) for i in range(n + 1) for f in rng.integers(0, N, nflick[i])]

        def poly_mask(spec, blur):
            pts = np.array([[float(v) for v in p.split(",")] for p in spec.split(";")]) * [W, H]
            m = np.zeros((H, W), np.float32); cv2.fillPoly(m, [pts.astype(np.int32)], 1.0)
            return cv2.GaussianBlur(m, (0, 0), blur)

        self.train = self.floor = None
        self.passes = []
        if train:
            self.train = poly_mask(train, 2 * sc)[..., None]
            self.floor = poly_mask(floor, 40 * sc)[..., None] if floor else None
            self.passes = [(abs(float(p)) * fps, p.strip().startswith("-")) for p in passes.split(",") if p]
            self.xs = np.arange(W, dtype=np.float32)
            self.tint = np.array([1.0, 0.97, 0.85], np.float32)        # BGR: pale cool-white carriage light
            _, xi = np.nonzero(self.train[..., 0] > 0.5); self.x0, self.x1 = float(xi.min()), float(xi.max())
            self.length = 2.2 * (self.x1 - self.x0)                    # longer than the glass, so it fills it mid-pass
            self.dur = 3.2 * fps                                       # frames from head entering to tail leaving
            for p, _ in self.passes:
                assert p + self.dur < N, "a train pass would cross the loop end"

        self.sweeps = [(abs(float(p)) * fps, p.strip().startswith("-")) for p in sweeps.split(",") if p]
        self.SW = 2.6 * fps                                     # frames a headlight band takes to cross the frame
        for p, _ in self.sweeps:
            assert p + self.SW + 1.5 * fps < N, "a sweep or its sign blink would cross the loop end"
        if self.sweeps:
            self.gy, self.gx = np.mgrid[0:H, 0:W].astype(np.float32)
            self.lift = cv2.GaussianBlur(img.mean(2), (0, 0), 6 * sc)[..., None]   # light lands harder on lit surfaces
        self.sign = None
        if blink:                                          # only the tubes and their glow dim, not the wall behind
            glow = np.clip(cv2.GaussianBlur(light.astype(np.float32), (0, 0), 5 * sc) * 1.6, 0, 1)
            self.sign = (poly_mask(blink, 12 * sc) * glow)[..., None]
        self.headlamp = np.array([1.0, 0.96, 0.9], np.float32)    # BGR: slightly cool white

    def gain(self, i):
        i %= self.N
        t = i / self.N
        v = (self.amp * np.sin(2 * np.pi * (self.k * t + self.ph))).sum(0)
        for li, f in self.fl:
            if 0 <= (i - f) % self.N < 3:
                v[li] = -2.2                                  # quick dip, 3 frames
        # soften the per-light gains so neighbouring cells blend (no square edges), then keep them on the lights only
        g = cv2.GaussianBlur(v[self.labels].astype(np.float32), (0, 0), 0.6 * self.c)
        return (1 + self.strength * g * self.weight)[..., None]

    def _sweep_light(self, i):
        """Soft slanted band of headlight light crossing the frame; eases in and out."""
        out = None
        W, H = self.W, self.H
        for p, rev in self.sweeps:
            d = (i - p) / self.SW
            if not 0 <= d <= 1:
                continue
            cx = (-0.25 + 1.5 * d) * W
            x = self.gx if not rev else W - self.gx
            u = x - cx + 0.35 * (self.gy - H / 2)               # slanted, like light through a window frame
            band = np.exp(-(u / (0.11 * W)) ** 2) * np.sin(np.pi * d) ** 2
            out = band if out is None else np.maximum(out, band)
        return out

    def _sign_gain(self, i):
        """Sign blinks twice (two short dips) 0.3 s after each sweep ends."""
        for p, _ in self.sweeps:
            d = i - (p + self.SW + 0.3 * self.fps)
            if 0 <= d < 3 or 7 <= d < 10:
                return 0.4
        return 1.0

    def _train_row(self, i):
        """1-D brightness across x of whatever train is in view at frame i (zeros when none)."""
        sc, W = self.sc, self.W
        out = np.zeros(W, np.float32)
        for p, rev in self.passes:
            d = i - p
            if not 0 <= d <= self.dur:
                continue
            head = self.x0 + (d / self.dur) * (self.length + (self.x1 - self.x0))   # head enters at x0, tail leaves past x1
            x = self.xs if not rev else (self.x0 + self.x1) - self.xs              # mirror for right-to-left
            inside = (x <= head) & (x >= head - self.length)
            win = 0.12 + 0.88 * (np.sin((x - head) / (46 * sc) * 2 * np.pi) > 0.1)  # carriage windows + pillars
            gap = ((head - x) % (self.length / 6)) > 22 * sc                          # dark gaps between cars
            out = np.maximum(out, inside * win * gap)
        return cv2.GaussianBlur(out[None, :], (0, 1), sigmaX=7 * sc)[0] if out.any() else out

    def frame(self, i):
        """Float BGR frame 0..1 with lights breathing (and train / sweeps when configured)."""
        frame = self.img * self.gain(i)
        if self.train is not None:
            row = self._train_row(i)
            if row.any():
                frame = frame + 0.32 * self.train * row[None, :, None] * self.tint
                if self.floor is not None:
                    frame = frame + 0.05 * self.floor * float(row.mean() / row.max()) * self.tint
        if self.sweeps:
            sl = self._sweep_light(i)
            if sl is not None:
                frame = frame + 0.55 * (0.25 + self.lift) * sl[..., None] * self.headlamp
            if self.sign is not None and (sg := self._sign_gain(i)) < 1:
                frame = frame * (1 - self.sign * (1 - sg))
        return np.clip(frame, 0, 1)


def animate(still, out, seconds=60, fps=24, size="1920x1080", seed=1, strength=0.3, exclude=None,
            train=None, floor=None, passes="", sweeps="", blink=None):
    """Write OUT.mp4 (AV1) of the still with only its lights moving. still/exclude are image paths."""
    lt = Lights(cv2.imread(str(still)), size, seconds, fps, seed, strength,
                cv2.imread(str(exclude), 0) if exclude else None, train, floor, passes, sweeps, blink)
    print(f"{lt.n} lights")
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{lt.W}x{lt.H}",
                           "-r", str(fps), "-i", "-", "-c:v", "libsvtav1", "-crf", "16", "-preset", "8", "-g", str(lt.N),
                           "-pix_fmt", "yuv420p10le", str(out)], stdin=subprocess.PIPE)
    for i in range(lt.N):
        ff.stdin.write((lt.frame(i) * 255).astype(np.uint8).tobytes())
        if i % 240 == 0:
            print(f"frame {i}/{lt.N}", flush=True)
    ff.stdin.close(); ff.wait()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("still"); ap.add_argument("out")
    ap.add_argument("--size", default="1920x1080"); ap.add_argument("--exclude")
    ap.add_argument("--seconds", type=float, default=60); ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--strength", type=float, default=0.3)
    ap.add_argument("--train"); ap.add_argument("--floor"); ap.add_argument("--passes", default="")
    ap.add_argument("--sweeps", default="", help="seconds at which a passing car's headlights sweep across the room; "
                    "negative = right-to-left")
    ap.add_argument("--blink", help="polygon of a sign that blinks twice after each sweep")
    a = ap.parse_args(argv)
    animate(a.still, a.out, a.seconds, a.fps, a.size, a.seed, a.strength, a.exclude, a.train, a.floor, a.passes, a.sweeps, a.blink)


if __name__ == "__main__":
    main()
