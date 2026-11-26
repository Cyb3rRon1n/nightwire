"""Building blocks for loops that don't feel repeated: whole cycle counts per loop that share no beat, and noise that
wraps around (spec "Can't tell it loops")."""

from math import gcd

import numpy as np


def pick_cycles(hz: float, seconds: float, taken: set[int]) -> int:
    """The count nearest hz*seconds (at least 1) that shares no factor with any count already taken; it is added."""
    want = max(1, round(hz * seconds))
    for d in range(0, 4 * want + 8):
        for c in (want + d, want - d):
            if c >= 1 and c not in taken and all(gcd(c, t) == 1 for t in taken):
                taken.add(c)
                return c
    raise ValueError(f"no free cycle count near {want}")


def divisors_between(n: int, lo: int, hi: int) -> list[int]:
    """Divisors of n within lo..hi; [n] when there are none, so a period always divides the loop."""
    out = [d for d in range(lo, hi + 1) if n % d == 0]
    return out or [n]


def tile_noise(h: int, w: int, cell: int, rng: np.random.Generator) -> np.ndarray:
    """Smooth 0..1 noise with features about `cell` px across that wraps around both edges (low-passed in Fourier
    space, so it is periodic by construction)."""
    f = np.fft.fft2(rng.standard_normal((h, w)))
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    f *= np.exp(-((fy ** 2 + fx ** 2) * (cell ** 2) * 4))
    n = np.fft.ifft2(f).real
    return ((n - n.min()) / (np.ptp(n) or 1)).astype(np.float32)
