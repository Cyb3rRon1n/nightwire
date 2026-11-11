"""Automatic QA for v2 character sheet sets (turnaround/portrait/expressions/... under wardrobe/<state>/).

check_set() returns a list of report lines; lines starting "FLAG" are problems, "ok"/"info" are not.
All checks are cheap colour heuristics (see the ponytail notes for their ceilings)."""

import argparse
import colorsys
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from tools.reference_library import split_figures

# ponytail: hue families are coarse; "black"/"white"-style neutrals use value/saturation only.
_HUES = {"red": (-20, 12), "crimson": (-20, 12), "auburn": (0, 25), "orange": (10, 40), "blonde": (35, 62), "blond": (35, 62),
         "golden": (35, 62), "gold": (35, 62), "yellow": (45, 70), "green": (75, 170), "teal": (165, 195), "aqua": (165, 195),
         "cyan": (165, 200), "blue": (190, 255), "purple": (255, 300), "violet": (255, 300), "lavender": (240, 290),
         "pink": (300, 345), "magenta": (290, 335)}
_NEUTRAL = {"black": lambda h, s, v: v < .28, "white": lambda h, s, v: (s < .15) & (v > .8),
            "silver": lambda h, s, v: (s < .15) & (v > .55), "grey": lambda h, s, v: (s < .15) & (v > .25) & (v < .8),
            "gray": lambda h, s, v: (s < .15) & (v > .25) & (v < .8), "brown": lambda h, s, v: (h > 5) & (h < 40) & (s > .35) & (v < .55)}
HAIR_TOL = {"hue": 12.0, "sat": .25, "val": .2}  # flag when turnaround and the other sheet differ by more than this
BACK_SKIN_RATIO = .5  # figure 3 head skin must be under this fraction of figure 1's, else it's a front view
OUTFIT_MIN = .6  # histogram intersection of figures 1 and 3 below this = different outfit
OUTFIT_BIN = .08  # ...or any one colour (hue bin) differing in share by more than this (a print or accent colour)
COVER_SKIN_MAX = .12  # skin share of the front figure's chest band


def _hsv(im: Image.Image) -> np.ndarray:
    """H in degrees 0-360, S and V in 0-1, shape (h, w, 3)."""
    a = np.asarray(im.convert("HSV")).astype(float)
    return np.stack([a[..., 0] * 360 / 255, a[..., 1] / 255, a[..., 2] / 255], axis=-1)


def _skin(im: Image.Image) -> np.ndarray:
    """Light peach/tan pixels: orange-ish hue, modest saturation (hair, leopard print and lips are more saturated)."""
    hsv = _hsv(im)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h < 50) | (h > 345)) & (s > .08) & (s < .55) & (v > .6)


def _foreground(im: Image.Image) -> np.ndarray:
    return np.abs(np.asarray(im.convert("RGB")).astype(int) - 128).sum(axis=2) > 24


def _hair_tag(design) -> str | None:
    for t in design.appearance.lower().replace(",", " ,").split(","):
        w = t.split()
        if w and w[-1] == "hair":
            for c in w[:-1]:
                if c in _HUES or c in _NEUTRAL:
                    return c
    return None


def _hair_mask(im: Image.Image, colour: str) -> np.ndarray:
    hsv = _hsv(im)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    if colour in _NEUTRAL:
        return _NEUTRAL[colour](h, s, v)
    lo, hi = _HUES[colour]
    return (((h - lo) % 360) <= (hi - lo)) & (s > .45) & (v > .15)


def hair_colour(im: Image.Image, colour: str, region: tuple[float, float] = (0, .5)) -> tuple[float, float, float] | None:
    """Median (hue deg, sat, val) of hair-family pixels in a vertical slice of the image; None if too few."""
    a = im.convert("RGB")
    y0, y1 = int(a.height * region[0]), int(a.height * region[1])
    crop = a.crop((0, y0, a.width, y1))
    m = _hair_mask(crop, colour)
    if m.mean() < .005:
        return None
    hsv = _hsv(crop)[m]
    ang = np.deg2rad(hsv[:, 0])  # circular median-ish: mean direction of the family pixels, robust enough inside a 30-60 degree family
    hue = float(np.rad2deg(np.arctan2(np.median(np.sin(ang)), np.median(np.cos(ang)))) % 360)
    return hue, float(np.median(hsv[:, 1])), float(np.median(hsv[:, 2]))


def _hue_delta(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def check_hair(set_dir: Path, design) -> list[str]:
    colour = _hair_tag(design)
    if not colour:
        return ["info hair: no hair colour tag in design appearance, skipped"]
    ta = set_dir / "turnaround.png"
    if not ta.exists():
        return ["info hair: no turnaround.png"]
    figs = split_figures(Image.open(ta))
    if not figs:
        return ["FLAG hair: no figure found in turnaround"]
    ref = hair_colour(figs[0], colour, (0, .15))
    if ref is None:
        return [f"FLAG hair: no {colour} hair pixels in the turnaround head"]
    out = [f"info hair ({colour}) turnaround: H{ref[0]:.0f} S{ref[1]:.2f} V{ref[2]:.2f}"]
    for name in ("portrait", "expressions"):
        p = set_dir / f"{name}.png"
        if not p.exists():
            continue
        got = hair_colour(Image.open(p), colour, (0, .5))
        if got is None:
            out.append(f"FLAG hair: no {colour} hair pixels in {name}")
            continue
        dh, ds, dv = _hue_delta(ref[0], got[0]), abs(ref[1] - got[1]), abs(ref[2] - got[2])
        if min(ref[1], got[1]) < .15 or min(ref[2], got[2]) < .1:
            dh = 0.0  # black/grey/silver hair: hue of near-neutral pixels is noise (v2 batch flagged every dark-haired set)
        bad = dh > HAIR_TOL["hue"] or ds > HAIR_TOL["sat"] or dv > HAIR_TOL["val"]
        out.append(f"{'FLAG' if bad else 'ok'} hair {name}: H{got[0]:.0f} S{got[1]:.2f} V{got[2]:.2f} (delta H{dh:.0f} S{ds:.2f} V{dv:.2f}; limits H{HAIR_TOL['hue']:.0f} S{HAIR_TOL['sat']} V{HAIR_TOL['val']})")
    return out


def _outfit_hist(fig: Image.Image) -> np.ndarray:
    """Torso colour histogram, non-skin figure pixels: dark, light-neutral, 12 hue bins."""
    w, h = fig.size
    crop = fig.crop((0, int(h * .25), w, int(h * .5)))
    keep = _foreground(crop) & ~_skin(crop)
    hsv = _hsv(crop)[keep]
    if not len(hsv):
        return np.zeros(14)
    dark = hsv[:, 2] < .25
    grey = ~dark & (hsv[:, 1] < .2)
    col = ~dark & ~grey
    hist = np.concatenate([[dark.sum(), grey.sum()], np.histogram(hsv[col, 0], bins=12, range=(0, 360))[0]]).astype(float)
    return hist / hist.sum()


def check_layout(set_dir: Path) -> list[str]:
    ta = set_dir / "turnaround.png"
    if not ta.exists():
        return ["info turnaround: missing"]
    figs = split_figures(Image.open(ta))
    if len(figs) != 3:
        return [f"FLAG turnaround: {len(figs)} figures found, expected 3"]
    out = ["ok turnaround: 3 figures"]

    def head_skin(f):
        top = f.crop((0, 0, f.width, int(f.height * .15)))
        return float((_skin(top) & _foreground(top)).sum() / max(1, _foreground(top).sum()))

    s1, s3 = head_skin(figs[0]), head_skin(figs[2])
    bad = s3 > BACK_SKIN_RATIO * s1 and s3 > .02
    out.append(f"{'FLAG' if bad else 'ok'} turnaround figure 3 {'looks like a FRONT view, expected back' if bad else 'looks like a back view'}"
               f" (head skin front {s1:.3f}, fig3 {s3:.3f})")
    h1, h3 = _outfit_hist(figs[0]), _outfit_hist(figs[2])
    overlap, worst = float(np.minimum(h1, h3).sum()), float(np.abs(h1[2:] - h3[2:]).max())
    bad = overlap < OUTFIT_MIN or worst > OUTFIT_BIN
    out.append(f"{'FLAG' if bad else 'ok'} turnaround outfit figure 1 vs 3 colour overlap {overlap:.2f} (min {OUTFIT_MIN}), worst hue-bin gap {worst:.2f} (max {OUTFIT_BIN})"
               + (": different clothing" if bad else ""))
    return out


def check_cover(set_dir: Path) -> list[str]:
    ta = set_dir / "turnaround.png"
    if not ta.exists():
        return []
    figs = split_figures(Image.open(ta))
    if not figs:
        return []
    f = figs[0]
    band = f.crop((int(f.width * .25), int(f.height * .2), int(f.width * .75), int(f.height * .42)))
    r = float((_skin(band) & _foreground(band)).mean())
    bad = r > COVER_SKIN_MAX
    return [f"{'FLAG' if bad else 'ok'} cover: chest-band skin {r:.3f} (max {COVER_SKIN_MAX})" + (": possible open jacket/cleavage" if bad else "")]


def check_set(set_dir, design, state: str = "") -> list[str]:
    set_dir = Path(set_dir)
    return check_hair(set_dir, design) + check_layout(set_dir) + check_cover(set_dir)


def fix_hair(set_dir, design, out_dir=None) -> list[Path]:
    """Write recoloured copies (<name>-fixed.png) of portrait/expressions with hair shifted to the turnaround's. Originals untouched."""
    set_dir = Path(set_dir)
    out_dir = Path(out_dir or set_dir)
    colour = _hair_tag(design)
    figs = split_figures(Image.open(set_dir / "turnaround.png"))
    ref = hair_colour(figs[0], colour, (0, .15)) if colour and figs else None
    if ref is None or colour in _NEUTRAL:
        return []  # ponytail: neutral (black/white/grey) hair has no hue to shift
    written = []
    for name in ("portrait", "expressions"):
        p = set_dir / f"{name}.png"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        got = hair_colour(im, colour)
        if got is None:
            continue
        hsv = _hsv(im)
        m = _hair_mask(im, colour)
        hsv[m, 0] = (hsv[m, 0] + ((ref[0] - got[0] + 180) % 360 - 180)) % 360
        hsv[m, 1] = np.clip(hsv[m, 1] * ref[1] / max(got[1], .05), 0, 1)
        hsv[m, 2] = np.clip(hsv[m, 2] * ref[2] / max(got[2], .05), 0, 1)
        arr = np.stack([hsv[..., 0] * 255 / 360, hsv[..., 1] * 255, hsv[..., 2] * 255], axis=-1).round().astype(np.uint8)
        dest = out_dir / f"{name}-fixed.png"
        Image.fromarray(arr, "HSV").convert("RGB").save(dest)
        written.append(dest)
    return written


def main(argv=None) -> int:
    from narrator.designs import load_designs
    ap = argparse.ArgumentParser(prog="python -m tools.sheet_qa")
    ap.add_argument("slug")
    ap.add_argument("--state")
    ap.add_argument("--design-dir", type=Path, default=Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")))
    ap.add_argument("--fix-hair", action="store_true", help="write <name>-fixed.png recoloured copies (never overwrites originals)")
    ap.add_argument("--out", type=Path, help="where --fix-hair writes (default: beside the originals)")
    a = ap.parse_args(argv)
    design = load_designs()[a.slug]
    root = a.design_dir / a.slug / "wardrobe"
    states = [a.state] if a.state else sorted(p.name for p in root.iterdir() if p.is_dir())
    bad = 0
    for st in states:
        d = root / st
        print(f"== {a.slug} / {st}")
        lines = check_set(d, design, st)
        bad += sum(l.startswith("FLAG") for l in lines)
        print("\n".join(lines))
        if a.fix_hair:
            for p in fix_hair(d, design, a.out):
                print(f"wrote {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
