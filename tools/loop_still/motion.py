"""Hair and coat stirring in the wind, and breathing, as displacement fields: every pixel is still the approved art,
only moved a little (spec "Character motion"). Each region has its own field and is warped as its own layer (coat
under hair). Roots move 0 and tips most, tips lag their roots (follow-through), and the face never moves. Every term
has whole cycles per loop, so frame N is frame 0."""

import cv2
import numpy as np

from tools.loop_still.periodic import pick_cycles

ORDER = ("coat", "hair")  # back to front
_TERMS = (0.7, 0.3)       # weights of the two sines per region
_LAG = 0.25               # tips run this many cycles behind their roots
_ACROSS = 0.3             # share of the sway across the wind
_SMOOTH = 3.0             # px, Gaussian on the field so no edge shears
_HOLD = 4.0               # px over which the field eases in from a held root or the face
_MAX_BEND = 0.06          # a tip moves at most this share of its distance from the roots
_SEAM = 1.0               # px per px of reach over which the outside field eases into its blurred copy
_FADE = 25                # the field fades out past the region over this many times its largest move (slope 1/25)


def _fit(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    w, h = size
    m = mask.astype(np.float32)
    if m.max() > 1:
        m = m / 255
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA if m.shape[1] > w else cv2.INTER_LINEAR)
    return np.clip(m, 0, 1)


def weights(region: np.ndarray, root: np.ndarray) -> np.ndarray:
    """0 at the root, 1 at the farthest tip, eased (** 1.5) so the middle stays calm; 0 outside the region."""
    inside = region >= 0.5
    if not inside.any() or not (root > 0).any():
        return np.zeros(region.shape, np.float32)
    d = cv2.distanceTransform(np.where(root > 0, 0, 255).astype(np.uint8), cv2.DIST_L2, 5)
    far = d[inside].max() or 1
    return np.where(inside, np.clip(d / far, 0, 1) ** 1.5, 0).astype(np.float32)


def _length(region: np.ndarray, root: np.ndarray) -> float:
    """The farthest a pixel of the region lies from its roots."""
    inside = region >= 0.5
    if not inside.any() or not (root > 0).any():
        return 0.0
    return float(cv2.distanceTransform(np.where(root > 0, 0, 255).astype(np.uint8), cv2.DIST_L2, 5)[inside].max())


def _roots(name: str, region: np.ndarray, face: np.ndarray) -> np.ndarray:
    inside = region >= 0.5
    ys = np.nonzero(inside.any(axis=1))[0]
    if not len(ys):
        return np.zeros(region.shape, np.float32)
    if name == "hair" and (face > 0).any():
        near = cv2.dilate((face > 0).astype(np.uint8), np.ones((13, 13), np.uint8)) > 0  # within 6 px of the face
        root = inside & near
        if root.any():
            return root.astype(np.float32)
    top = ys[0] + max(1, int(0.08 * (ys[-1] - ys[0] + 1)))  # the shoulder line, or the top of a faceless region
    root = inside.copy()
    root[top:] = False
    return root.astype(np.float32)


def _extend(field: np.ndarray, region: np.ndarray, reach: float) -> np.ndarray:
    """Carry the field past the region's edge, fading over `reach` px, so a strand can move out over what's behind.
    Right at the edge it takes the nearest region pixel's value (no step at the edge); farther out it eases into a
    blurred copy, so there is no seam where two parts of a coat meet."""
    inside = (region >= 0.5).astype(np.uint8)
    if not inside.any() or reach <= 0:
        return field
    dist, labels = cv2.distanceTransformWithLabels(1 - inside, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    zy, zx = np.nonzero(inside)  # the source's zero pixels; label k is the k-th of them in row-major order
    order = np.zeros(labels.max() + 1, np.int64)
    order[1:len(zy) + 1] = zy * field.shape[1] + zx
    near = field.reshape(-1)[order[labels]]
    soft = max(8.0, _SEAM * reach)
    smooth = cv2.GaussianBlur(near, (0, 0), soft / 2)
    t = np.clip(dist / soft, 0, 1)
    out = (near * (1 - t) + smooth * t) * np.clip(1 - dist / (_FADE * reach), 0, 1)
    return np.where(inside > 0, field, out).astype(np.float32)


def _hold(*masks: np.ndarray) -> np.ndarray:
    """1 away from the held pixels, easing to exactly 0 on them."""
    held = np.zeros(masks[0].shape, bool)
    for m in masks:
        held |= m > 0
    if not held.any():
        return np.ones(held.shape, np.float32)
    d = cv2.distanceTransform((~held).astype(np.uint8), cv2.DIST_L2, 5)
    t = np.clip(d / _HOLD, 0, 1)
    return (t * t * (3 - 2 * t)).astype(np.float32)


class _Region:
    def __init__(self, mask, roots):
        self.mask, self.roots = mask, roots
        self.terms: list[tuple[int, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        self.reach = 0.0


class Motion:
    def __init__(self, regions: dict, face: np.ndarray, size: tuple[int, int], frames: int, seconds: float,
                 wind: tuple[float, float], seed: int, taken: set, amp: float = 0.015, hz: float = 0.3,
                 breath: float = 0.004):
        self.W, self.H = size
        self.N = frames
        rng = np.random.default_rng(seed)
        face = _fit(face, size) if face is not None else np.zeros((self.H, self.W), np.float32)
        wx, wy = np.array(wind, np.float32) / (np.hypot(*wind) or 1)
        self.roots = np.zeros((self.H, self.W), np.float32)
        self.cycles: dict[str, list[int]] = {}
        self.regions: dict[str, _Region] = {}
        for name in sorted(regions, key=lambda n: ORDER.index(n) if n in ORDER else len(ORDER)):
            mask = _fit(regions[name], size)
            if not (mask >= 0.5).any():
                continue
            roots = _roots(name, mask, face)
            self.roots = np.maximum(self.roots, roots)
            r = self.regions[name] = _Region(mask, roots)
            # Tips move amp of the image height, but never more than _MAX_BEND of their own length from the roots:
            # a short bob that swung as far as long hair would tear (soak of rin-kageyama--alley, 2026-11-26).
            length = _length(mask, roots)
            px = min(amp * self.H, _MAX_BEND * length)
            move = px * sum(_TERMS) * (1 + _ACROSS)
            r.reach = move
            w = _extend(weights(mask, roots), mask, move)
            wind_hold, breath_hold = _hold(face, roots), _hold(face)

            def add(c, theta, maps, hold):  # maps: P, Q for x, then P, Q for y; smoothed between two holds
                r.terms.append((c, theta, *(cv2.GaussianBlur(m * hold, (0, 0), _SMOOTH) * hold for m in maps)))

            lag = 2 * np.pi * _LAG * w
            p, q = w * np.cos(lag), w * np.sin(lag)
            self.cycles[name] = []
            for k, a in enumerate(_TERMS):
                c = pick_cycles(hz * (1.0, 1.7)[k], seconds, taken)
                self.cycles[name].append(c)
                s = a * px
                ax, ay = s * (wx - _ACROSS * wy), s * (wy + _ACROSS * wx)
                add(c, rng.uniform(0, 2 * np.pi), (ax * p, ax * q, ay * p, ay * q), wind_hold)
            if name == "coat" and breath:
                ys = np.nonzero((mask >= 0.5).any(axis=1))[0]
                top, bottom = ys[0], ys[-1]
                rise = breath * (bottom - top)
                wb = np.clip((bottom - np.arange(self.H, dtype=np.float32)) / max(1, bottom - top), 0, 1)[:, None]
                wb = _extend(np.where(mask >= 0.5, wb, 0).astype(np.float32), mask, max(rise, 1))
                c = pick_cycles(0.25, seconds, taken)
                self.cycles["breath"] = [c]
                zero = np.zeros_like(wb)
                add(c, 0.0, (zero, zero, rise * wb, zero), breath_hold)
                r.reach += rise

    def field(self, i: int, name: str | None = None) -> tuple[np.ndarray, np.ndarray]:
        """One region's displacement in px at frame i, or the region's fields added up when name is None."""
        dx = np.zeros((self.H, self.W), np.float32)
        dy = np.zeros((self.H, self.W), np.float32)
        for n, r in self.regions.items():
            if name is not None and n != name:
                continue
            for c, theta, px, qx, py, qy in r.terms:
                a = 2 * np.pi * c * i / self.N + theta
                sa, ca = np.float32(np.sin(a)), np.float32(np.cos(a))
                dx += sa * px - ca * qx
                dy += sa * py - ca * qy
        return dx, dy

    def _remap(self, img, dx, dy, how=cv2.INTER_LINEAR):
        if not hasattr(self, "_grid"):
            self._grid = np.meshgrid(np.arange(self.W, dtype=np.float32), np.arange(self.H, dtype=np.float32))
        gx, gy = self._grid
        return cv2.remap(img, gx - dx, gy - dy, how, borderMode=cv2.BORDER_REFLECT)

    def layers(self, img: np.ndarray, i: int) -> list[tuple[np.ndarray, np.ndarray]]:
        """(warped image, warped region alpha) per region, back to front."""
        out = []
        for name, r in self.regions.items():
            dx, dy = self.field(i, name)
            # Bicubic for the art: a 1-2 px ink line moved by a fraction of a pixel stays a line (bilinear smears it).
            moved = np.clip(self._remap(img, dx, dy, cv2.INTER_CUBIC), 0, 1) if img.dtype == np.float32 \
                else self._remap(img, dx, dy, cv2.INTER_CUBIC)
            out.append((moved, np.clip(self._remap(r.mask, dx, dy), 0, 1)))
        return out

    def warp(self, img: np.ndarray, i: int) -> np.ndarray:
        """The moved regions laid over the image as it is (the render lays them over an inpainted plate instead)."""
        out = img
        for moved, alpha in self.layers(img, i):
            a = alpha[..., None] if img.ndim == 3 else alpha
            out = out * (1 - a) + moved * a
        return out.astype(img.dtype) if self.regions else img

    def stretch(self, i: int) -> tuple[float, float]:
        """Min and max local stretch over every region and the area its pixels can reach, at frame i."""
        lo, hi = 1.0, 1.0
        for name, r in self.regions.items():
            k = 2 * int(np.ceil(r.reach)) + 1
            near = cv2.dilate((r.mask >= 0.5).astype(np.uint8), np.ones((k, k), np.uint8)) > 0
            a, b = stretch(*self.field(i, name), near)
            lo, hi = min(lo, a), max(hi, b)
        return lo, hi


def stretch(dx: np.ndarray, dy: np.ndarray, where: np.ndarray | None = None) -> tuple[float, float]:
    """Min and max local area change (Jacobian determinant) of the map p -> p + d, optionally only where given."""
    dxy, dxx = np.gradient(dx)
    dyy, dyx = np.gradient(dy)
    det = (1 + dxx) * (1 + dyy) - dxy * dyx
    if where is not None:
        det = det[where] if where.any() else np.ones(1, np.float32)
    return float(det.min()), float(det.max())
