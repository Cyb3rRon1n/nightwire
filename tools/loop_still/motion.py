"""Hair and coat stirring in the wind, and breathing, as displacement fields: every pixel is still the approved art,
only moved a little (spec "Character motion"). Each region has its own field and is warped as its own layer (coat
under hair). Roots move 0 and tips most, tips lag their roots (follow-through), and the face never moves. Every term
has whole cycles per loop, so frame N is frame 0."""

import cv2
import numpy as np

from tools.loop_still.idle import SPRING, respond, spring
from tools.loop_still.periodic import pick_cycles

ORDER = ("coat", "hair")  # back to front
_TERMS = (0.7, 0.3)       # weights of the two sines per region
_LAG = 0.25               # tips run this many cycles behind their roots
_ACROSS = 0.3             # share of the sway across the wind
_SMOOTH = 3.0             # px, Gaussian on the field so no edge shears
_HOLD = 4.0               # px over which the field eases in from a held root or the face
_MAX_BEND = 0.045         # a tip moves at most this share of its distance from the roots
_SEAM = 3.0               # px per px of reach over which the outside field eases into its blurred copy
_FADE = 25                # the field fades out past the region over this many times its largest move (slope 1/25)


def _fit(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    w, h = size
    m = mask.astype(np.float32)
    if m.max() > 1:
        m = m / 255
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA if m.shape[1] > w else cv2.INTER_LINEAR)
    return np.clip(m, 0, 1)


def weights(region: np.ndarray, root: np.ndarray, hanging: bool = False) -> np.ndarray:
    """0 at the root, 1 at the farthest tip, eased (** 1.5) so the middle stays calm; 0 outside the region.
    hanging: cloth hangs from a shoulder line, so only the height below the root's lowest row counts (distance from a
    narrow hood top would bend a hem sideways)."""
    inside = region >= 0.5
    if not inside.any() or not (root > 0).any():
        return np.zeros(region.shape, np.float32)
    if hanging:
        line = np.nonzero((root > 0).any(axis=1))[0].max()
        d = np.broadcast_to(np.clip(np.arange(region.shape[0], dtype=np.float32) - line, 0, None)[:, None],
                            region.shape).copy()
    else:
        d = cv2.distanceTransform(np.where(root > 0, 0, 255).astype(np.uint8), cv2.DIST_L2, 5)
    far = d[inside].max() or 1
    return np.where(inside, np.clip(d / far, 0, 1) ** 1.5, 0).astype(np.float32)


def _length(region: np.ndarray, root: np.ndarray, hanging: bool = False) -> float:
    """The farthest a pixel of the region lies from its roots (below the shoulder line, for hanging cloth)."""
    inside = region >= 0.5
    if not inside.any() or not (root > 0).any():
        return 0.0
    if hanging:
        return float(np.nonzero(inside.any(axis=1))[0].max() - np.nonzero((root > 0).any(axis=1))[0].max())
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
    near = cv2.GaussianBlur(near, (0, 0), max(2.0, reach / 4))  # a ragged edge would fan out into the field
    soft = max(8.0, _SEAM * reach)
    smooth = cv2.GaussianBlur(near, (0, 0), soft / 2)
    t = np.clip(dist / soft, 0, 1)
    out = (near * (1 - t) + smooth * t) * np.clip(1 - dist / (_FADE * reach), 0, 1)
    return np.where(inside > 0, field, out).astype(np.float32)


def _hold(*masks: np.ndarray, ease: float = _HOLD) -> np.ndarray:
    """1 away from the held pixels, easing to exactly 0 on them over `ease` px."""
    held = np.zeros(masks[0].shape, bool)
    for m in masks:
        held |= m > 0
    if not held.any():
        return np.ones(held.shape, np.float32)
    d = cv2.distanceTransform((~held).astype(np.uint8), cv2.DIST_L2, 5)
    t = np.clip(d / ease, 0, 1)
    return (t * t * (3 - 2 * t)).astype(np.float32)


class _Region:
    def __init__(self, mask, roots):
        self.mask, self.roots = mask, roots
        self.terms: list[tuple[int, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        self.reach = 0.0


class Motion:
    def __init__(self, regions: dict, face: np.ndarray, size: tuple[int, int], frames: int, seconds: float,
                 wind: tuple[float, float], seed: int, taken: set, amp: float = 0.01, hz: float = 0.3,
                 breath: float = 0.004, idle=None, body: np.ndarray | None = None):
        """idle (tools.loop_still.idle.Idle) adds a "body" layer, drawn first, that carries the rest of her (`body`, a
        mask) on the idle field; hair and coat ride the same field and their tips follow it through springs."""
        self.W, self.H = size
        self.N = frames
        self.seconds = seconds
        self.idle = idle
        rng = np.random.default_rng(seed)
        face = _fit(face, size) if face is not None else np.zeros((self.H, self.W), np.float32)
        wx, wy = np.array(wind, np.float32) / (np.hypot(*wind) or 1)
        self.roots = np.zeros((self.H, self.W), np.float32)
        self.cycles: dict[str, list[int]] = dict(idle.cycles) if idle else {}
        self.regions: dict[str, _Region] = {}
        if idle is not None:
            b = self.regions["body"] = _Region(_fit(body if body is not None else face, size),
                                               np.zeros((self.H, self.W), np.float32))
            b.terms = idle.terms()
            b.reach = idle.reach
        for name in sorted(regions, key=lambda n: ORDER.index(n) if n in ORDER else len(ORDER)):
            mask = _fit(regions[name], size)
            if not (mask >= 0.5).any():
                continue
            roots = _roots(name, mask, face)
            self.roots = np.maximum(self.roots, roots)
            r = self.regions[name] = _Region(mask, roots)
            # Tips move amp of the image height, but never more than _MAX_BEND of their own length from the roots:
            # a short bob that swung as far as long hair would tear (soak of rin-kageyama--alley, 2026-11-26).
            hanging = name != "hair"
            length = _length(mask, roots, hanging)
            px = min(amp * self.H, _MAX_BEND * length)
            move = px * sum(_TERMS) * (1 + _ACROSS)
            r.reach = move
            if hanging:  # the height profile itself continues past the edge: no slant from a diagonal hem
                full = weights(np.ones_like(mask), roots, hanging=True)
                full = np.clip(full / max(full[mask >= 0.5].max(), 1e-6), 0, 1)
                out = cv2.distanceTransform((mask < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
                w = np.where(mask >= 0.5, full, full * np.clip(1 - out / (_FADE * move), 0, 1)).astype(np.float32)
            else:
                w = _extend(weights(mask, roots), mask, move)
            wind_hold = _hold(face, roots)

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
                # the shoulders rise but the face doesn't: ease the lift out over 20x its size beside the face
                breath_hold = _hold(face, ease=max(_HOLD, 20 * rise))
                wb = np.clip((bottom - np.arange(self.H, dtype=np.float32)) / max(1, bottom - top), 0, 1)[:, None]
                wb = _extend(np.where(mask >= 0.5, wb, 0).astype(np.float32), mask, max(rise, 1))
                c = pick_cycles(0.25, seconds, taken)
                self.cycles["breath"] = [c]
                zero = np.zeros_like(wb)
                add(c, 0.0, (zero, zero, rise * wb, zero), breath_hold)
                r.reach += rise
            if idle is not None:  # ride the body, and let the tips trail it like a spring
                f0, zeta = SPRING.get(name, SPRING["coat"])
                inside = mask >= 0.5
                for t in idle.terms(hair=name == "hair"):
                    for u in (t, respond(t, spring(t[0], seconds, f0, zeta), w)):
                        r.terms.append(u)
                        r.reach += float(np.sqrt(u[2] ** 2 + u[3] ** 2 + u[4] ** 2 + u[5] ** 2)[inside].max())

    def field(self, i: int, name: str | None = None) -> tuple[np.ndarray, np.ndarray]:
        """One region's displacement in px at frame i, or the region's fields added up when name is None. A region's
        field is kept for the frame, so layers, stretch and the drips share one computation (don't change it)."""
        if name is not None:
            if getattr(self, "_ci", None) != i:
                self._ci, self._cache = i, {}
            if name not in self._cache:
                self._cache[name] = self._field(i, name)
            return self._cache[name]
        return self._field(i, None)

    def offsets(self, i: int) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        return {n: self.field(i, n) for n in self.regions}

    def _field(self, i: int, name: str | None) -> tuple[np.ndarray, np.ndarray]:
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

    def move(self, mask: np.ndarray, i: int) -> np.ndarray:
        """A mask (or image) carried on the body's idle field at frame i; unchanged without an idle."""
        if "body" not in self.regions:
            return mask
        return self._remap(mask, *self.field(i, "body"))

    def rigid_error(self, i: int) -> float:
        """How far the body field over the face is from a shift plus rotation, in px (0 without an idle)."""
        return self.idle.rigid_error(self.field(i, "body")) if self.idle is not None else 0.0

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
        """Min and max local stretch of the moved art that is visible at frame i (where the warped region shows)."""
        lo, hi = 1.0, 1.0
        for name, r in self.regions.items():
            dx, dy = self.field(i, name)
            a, b = stretch(dx, dy, self._remap(r.mask, dx, dy) >= 0.5)
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
