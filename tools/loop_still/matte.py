"""The character's cut-out, made once with a BiRefNet-family ONNX model and cached beside the still as
<still>.matte.png, so it can be fixed by hand (spec 2026-11-25-layered-loop-design.md, "Matte")."""

from pathlib import Path

import cv2
import numpy as np

MATTE_SUFFIX = ".matte.png"
_SIDE = 1024
_MEAN, _STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)


def matte_path(still: Path) -> Path:
    return still.with_name(still.stem + MATTE_SUFFIX)


def _infer(img_bgr: np.ndarray, model: Path) -> np.ndarray:
    import onnxruntime as ort  # late: only needed when a matte is made
    sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    x = cv2.resize(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB), (_SIDE, _SIDE), interpolation=cv2.INTER_AREA)
    x = ((x.astype(np.float32) / 255 - _MEAN) / _STD).transpose(2, 0, 1)[None]
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    if out.min() < -0.01 or out.max() > 1.01:  # logits (a sigmoid output can overshoot 0..1 by rounding)
        out = 1 / (1 + np.exp(-np.clip(out, -50, 50)))
    out = np.clip(out, 0, 1)
    return cv2.resize(out.astype(np.float32), img_bgr.shape[1::-1], interpolation=cv2.INTER_LINEAR)


def load_or_make_matte(still: Path, model: Path | None, redo: bool = False) -> np.ndarray:
    """Float32 HxW 0..1 at the still's size. A cached matte is reused and never overwritten unless redo."""
    still, cached = Path(still), matte_path(Path(still))
    img = cv2.imread(str(still))
    if img is None:
        raise FileNotFoundError(still)
    if cached.exists() and not redo:
        a = cv2.imread(str(cached), cv2.IMREAD_GRAYSCALE)
        return cv2.resize(a, img.shape[1::-1], interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    if model is None or not Path(model).exists():
        raise FileNotFoundError(f"no matte model at {model}; pass --matte-model (see tools/loop_still/MODELS.md)")
    a = _infer(img, Path(model))
    cv2.imwrite(str(cached), (np.clip(a, 0, 1) * 255).round().astype(np.uint8))
    return a


def feather(matte: np.ndarray, px: int = 2) -> np.ndarray:
    """Soften only the edge: pixels farther than px from it keep their value."""
    hard = (matte >= 0.5).astype(np.uint8)
    inside = cv2.distanceTransform(hard, cv2.DIST_L2, 3)
    outside = cv2.distanceTransform(1 - hard, cv2.DIST_L2, 3)
    signed = np.where(hard > 0, inside - 0.5, 0.5 - outside)
    return np.clip(0.5 + signed / (2 * px), 0, 1).astype(np.float32)


def decontaminate(img: np.ndarray, matte: np.ndarray, ring_px: int = 3) -> np.ndarray:
    """Pull the inner edge ring's colour down toward her nearby inner colour where it is brighter (neon spill),
    so no halo shows when rain or light passes behind. Everything else is returned unchanged."""
    hard = (matte >= 0.5).astype(np.uint8)
    depth = cv2.distanceTransform(hard, cv2.DIST_L2, 3)
    ring = (hard > 0) & (depth <= ring_px)
    if not ring.any():
        return img
    core = ((hard > 0) & ~ring).astype(np.float32)
    k = (4 * ring_px + 1, 4 * ring_px + 1)
    num = cv2.blur(img * core[..., None], k)
    den = cv2.blur(core, k)[..., None]
    inner = np.where(den > 1e-3, num / np.maximum(den, 1e-3), img)
    out = img.copy()
    out[ring] = np.minimum(img[ring], inner[ring])
    return out
