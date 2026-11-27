"""The loop's checks, fed frame by frame while it renders and saved in meta.json (spec "Checks" and "Can't tell it
loops"): the face never changes, nothing stretches, the seam is a normal step, no glow leaks at her edge, and no
shorter repeat hides inside the loop."""

import cv2
import numpy as np

LIMITS = {"stretch": (0.9, 1.1), "seam": 1.25, "halo": (0.96, 1.04), "repeat": 1.0, "rigid": 0.05}
_SMALL_W = 96


def _small(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.astype(np.float32)
    h = max(1, round(g.shape[0] * _SMALL_W / g.shape[1]))
    return cv2.resize(g, (_SMALL_W, h), interpolation=cv2.INTER_AREA)


class Checks:
    def __init__(self, still: np.ndarray, face: np.ndarray, matte: np.ndarray, frames: int, fps: int,
                 blink_mask: np.ndarray | None = None, ring_skip: np.ndarray | None = None):
        self.still, self.N, self.fps = still.astype(np.float32), frames, fps
        held = face > 0
        if blink_mask is not None:
            held &= ~(blink_mask > 0)
        self.face = held if held.any() else None
        hard = (matte >= 0.5).astype(np.uint8)
        ring = (cv2.dilate(hard, np.ones((7, 7), np.uint8)) > 0) & (hard == 0)  # 3 px just outside her
        self.keep = ~(ring_skip > 0) if ring_skip is not None else np.ones(hard.shape, bool)
        ring &= self.keep  # where moving hair or cloth may pass, a brighter ring is the cloth, not a leak
        self.ring = ring if ring.any() and hard.any() else None
        self.ripple_diff = None
        self.ring_still = float(self.still[self.ring].mean()) if self.ring is not None else None
        self.face_diff = 0.0 if self.face is not None else None
        self.rigid_err = 0.0 if self.face is not None else None
        self.ring_sum, self.ring_ref, self.ring_n = 0.0, 0.0, 0
        self.lo, self.hi = 1.0, 1.0
        self.small: list[np.ndarray | None] = [None] * frames

    def character(self, i: int, char_img: np.ndarray, ref: np.ndarray | None = None,
                  where: np.ndarray | None = None) -> None:
        """The character as composited, before anything is drawn in front of her. With an idle the face has moved:
        `ref` is the still carried on her field and `where` the face as it lies now."""
        if self.face is None:
            return
        ref, where = (self.still, self.face) if ref is None else (ref, where)
        if where.any():
            self.face_diff = max(self.face_diff, float(np.abs(char_img[where] - ref[where]).max()))

    def rigid(self, err: float) -> None:
        """How far the face's motion this frame is from a shift plus rotation, in px."""
        if self.rigid_err is not None:
            self.rigid_err = max(self.rigid_err, err)

    def back(self, i: int, back_img: np.ndarray, city: np.ndarray | None = None, ring: np.ndarray | None = None) -> None:
        """Back layers and the character, before the front layers. With the same frame's city (the street without
        her), the ring is measured against it, so rain and fog behind her are not counted as a leak. `ring`: the ring
        as it lies this frame, when she moves."""
        if self.ring is not None:
            r = self.ring if ring is None else (ring & self.keep)
            if not r.any():
                return
            self.ring_sum += float(back_img[r].mean())
            self.ring_ref += float(city[r].mean()) if city is not None else self.ring_still
            self.ring_n += 1

    def ripples(self, leak: float) -> None:
        """How much of her the street ripples sampled into the street this frame (must stay 0)."""
        self.ripple_diff = max(self.ripple_diff or 0.0, leak)

    def stretch(self, lo: float, hi: float) -> None:
        self.lo, self.hi = min(self.lo, lo), max(self.hi, hi)

    def final(self, i: int, frame: np.ndarray) -> None:
        self.small[i] = _small(frame)

    def _seam_and_repeat(self) -> tuple[float | None, float | None]:
        frames = [f for f in self.small if f is not None]
        if len(frames) < 3:
            return None, None
        f = np.stack(frames)
        steps = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
        med = float(np.median(steps))
        seam = float(np.abs(f[0] - f[-1]).mean())
        if med < 1e-6:  # a still image: nothing moves, so nothing can show a seam or a repeat
            return (0.0 if seam < 1e-6 else float("inf")), None
        lags = range(self.fps, len(f) - self.fps + 1)
        repeat = min((float(np.abs(f - np.roll(f, -k, axis=0)).mean()) for k in lags), default=None)
        return seam / med, (repeat / med if repeat is not None else None)

    def result(self) -> dict:
        seam, repeat = self._seam_and_repeat()
        halo = self.ring_sum / self.ring_ref if self.ring_n and self.ring_ref else None
        out = {"face_max_diff": self.face_diff, "stretch_min": round(self.lo, 4), "stretch_max": round(self.hi, 4),
               "seam_ratio": None if seam is None else round(seam, 3),
               "halo_ratio": None if halo is None else round(halo, 4),
               "repeat_score": None if repeat is None else round(repeat, 3),
               "ripples_on_her": self.ripple_diff,
               "face_rigid": None if self.rigid_err is None else round(self.rigid_err, 4)}
        failed = []
        if self.face_diff:
            failed.append("face")
        if not LIMITS["stretch"][0] <= self.lo or not self.hi <= LIMITS["stretch"][1]:
            failed.append("stretch")
        if seam is not None and seam > LIMITS["seam"]:
            failed.append("seam")
        if halo is not None and not LIMITS["halo"][0] <= halo <= LIMITS["halo"][1]:
            failed.append("halo")
        if self.ripple_diff:
            failed.append("ripples_on_her")
        if self.rigid_err is not None and self.rigid_err > LIMITS["rigid"]:
            failed.append("face_rigid")
        if repeat is not None and repeat < LIMITS["repeat"]:
            failed.append("repeat")
        return {**out, "passed": not failed, "failed": failed}
