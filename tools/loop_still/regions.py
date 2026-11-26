"""Hair, coat and face masks for a still, made once with SAM 2 point prompts on the CPU and saved beside it, so they
can be fixed by hand (spec "Character motion", "Regions").

    python -m tools.loop_still.regions STILL --hair X,Y[;X,Y] --coat X,Y[;X,Y] --face X,Y[;X,Y]
                                       [--coat-not X,Y[;X,Y]] [--hair-not ...] [--face-not ...] [--redo]

Points are fractions of width and height; the --*-not points mark what a region is not (SAM 2 negative points). Needs the `loops` extra (torch, sam2) and the SAM 2.1 hiera-tiny checkpoint
(tools/loop_still/MODELS.md). Writes <still>.hair.png, <still>.coat.png, <still>.face.png.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from tools.loop_still.matte import load_or_make_matte

NAMES = ("hair", "coat", "face")
CHECKPOINT = Path.home() / "models/loop_still/sam2/sam2.1_hiera_tiny.pt"
CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"


def region_path(still: Path, name: str) -> Path:
    return still.with_name(f"{still.stem}.{name}.png")


def load_regions(still: Path) -> dict[str, np.ndarray]:
    """The saved masks that exist, as float32 0..1 at the still's size (a hand-fixed mask may be saved at another
    size or aspect; it must line up with the still before both are cropped to the output)."""
    out = {}
    size = None
    for name in NAMES:
        p = region_path(Path(still), name)
        if p.exists():
            if size is None:
                size = cv2.imread(str(still)).shape[1::-1]
            m = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            out[name] = cv2.resize(m, size, interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255 \
                if m.shape[::-1] != size else m.astype(np.float32) / 255
    return out


def clean_regions(hair, coat, face, matte):
    """A pixel belongs to one region: the face is never hair or coat, hair wins over coat, both stay inside the
    character's matte."""
    face = face.astype(np.float32)
    hair = _main_parts(np.minimum(hair, matte) * (1 - face))
    coat = _main_parts(np.minimum(coat, matte) * (1 - face) * (1 - hair))
    return hair.astype(np.float32), coat.astype(np.float32), face


def _main_parts(mask: np.ndarray, share: float = 0.02) -> np.ndarray:
    """Drop stray specks: pieces smaller than `share` of the biggest piece (SAM 2 leaves a few on shiny cloth)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats((mask >= 0.5).astype(np.uint8), connectivity=8)
    if n <= 2:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    small = np.nonzero(areas < share * areas.max())[0] + 1
    return np.where(np.isin(labels, small), 0, mask).astype(np.float32)


def _points(spec: str, w: int, h: int) -> np.ndarray:
    return np.array([[float(x) * w, float(y) * h] for x, y in (p.split(",") for p in spec.split(";"))], np.float32)


def _predict(img_rgb: np.ndarray, prompts: dict[str, str], negatives: dict[str, str]) -> dict[str, np.ndarray]:
    import torch  # late: the `loops` extra
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    predictor = SAM2ImagePredictor(build_sam2(CONFIG, str(CHECKPOINT), device="cpu"))
    h, w = img_rgb.shape[:2]
    out = {}
    with torch.inference_mode():
        predictor.set_image(img_rgb)
        for name, spec in prompts.items():
            pts = _points(spec, w, h)
            labels = np.ones(len(pts))
            if negatives.get(name):
                neg = _points(negatives[name], w, h)
                pts, labels = np.vstack([pts, neg]), np.concatenate([labels, np.zeros(len(neg))])
            masks, scores, _ = predictor.predict(point_coords=pts, point_labels=labels, multimask_output=True)
            out[name] = masks[int(np.argmax(scores))].astype(np.float32)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("still")
    for name in NAMES:
        ap.add_argument(f"--{name}", required=True, help="X,Y[;X,Y] as fractions of width,height")
        ap.add_argument(f"--{name}-not", help="points that are not this region")
    ap.add_argument("--matte-model")
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args(argv)
    still = Path(a.still)
    if not a.redo and any(region_path(still, n).exists() for n in NAMES):
        raise SystemExit("masks already exist beside the still; fix them by hand or pass --redo")
    img = cv2.imread(str(still))
    matte = load_or_make_matte(still, Path(a.matte_model) if a.matte_model else None)
    got = _predict(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), {n: getattr(a, n) for n in NAMES},
                   {n: getattr(a, f"{n}_not") for n in NAMES})
    for name, m in zip(NAMES, clean_regions(got["hair"], got["coat"], got["face"], matte)):
        cv2.imwrite(str(region_path(still, name)), (m * 255).round().astype(np.uint8))
        print(region_path(still, name))


if __name__ == "__main__":
    main()
