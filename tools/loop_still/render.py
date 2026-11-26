"""One still in, one seamless loop out (spec 2026-11-25-layered-loop-design.md). Back to front, every frame:

    city   = lights breathing on the plate (the still with the moving regions' area inpainted) + far rain + fog
    body   = the still's character that never moves, over the city (feathered matte; the face is exact)
    layers = hair and coat, warped (tools.loop_still.motion), then blinks
    tint   = optional light from the city on her edge
    front  = splashes + near rain

A lossless FFV1 master is written first; the mp4, the 3x preview, the poster and meta.json come from it."""

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from tools.lights import Lights, cover
from tools.loop_still.blink import load_blinks
from tools.loop_still.checks import Checks
from tools.loop_still.layers import Fog, Rain, Splashes
from tools.loop_still.matte import decontaminate, feather, load_or_make_matte
from tools.loop_still.motion import Motion
from tools.loop_still.regions import load_regions
from tools.shorts.remote import h264_encoder

MODELS = Path.home() / "models/loop_still"
DEFAULT_MATTE = MODELS / "birefnet-general.onnx"
LAMA = MODELS / "lama/lama_fp32.onnx"
RAIN_TINT = np.array([1.0, 0.95, 0.8], np.float32)  # cool blue-white, BGR
SPLASH_TINT = np.array([0.9, 0.9, 0.85], np.float32)


@dataclass
class Options:
    still: Path
    seconds: float = 20
    fps: int = 24
    size: str = "1920x1338"
    rain: str = "steady"
    near_rain: bool = True
    lights: bool = False
    strength: float = 0.3
    train: str | None = None
    floor: str | None = None
    passes: str = ""
    sweeps: str = ""
    sign_blink: str | None = None
    fog: bool = False
    ground: float = 0.8
    splashes: int = 40
    motion: str = "hair,coat,breath"
    still_character: bool = False
    blink: bool | None = None       # None: on when both eye patches exist
    edge_tint: bool = False
    plate: str = "lama"             # lama | telea
    matte_model: Path | None = None
    redo_matte: bool = False
    seed: int = 1
    preset: str | None = None
    out: Path | None = None
    frames_only: int = 0
    log: list = field(default_factory=list)


def _say(o: Options, msg: str) -> None:
    print(msg, flush=True)
    o.log.append(msg)


def _fit_mask(m: np.ndarray, w: int, h: int) -> np.ndarray:
    return np.clip(cover(m.astype(np.float32), w, h), 0, 1)


def _lama(img: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """LaMa (Apache-2.0) on a square crop around the hole, at its fixed 512 px."""
    import onnxruntime as ort  # late: only for a plate
    sess = ort.InferenceSession(str(LAMA), providers=["CPUExecutionProvider"])
    ys, xs = np.nonzero(hole)
    h, w = hole.shape
    side = min(max(ys.ptp(), xs.ptp()) + 64, max(h, w))
    cy, cx = (ys.min() + ys.max()) // 2, (xs.min() + xs.max()) // 2
    t, l = int(np.clip(cy - side // 2, 0, max(0, h - side))), int(np.clip(cx - side // 2, 0, max(0, w - side)))
    crop, m = img[t:t + side, l:l + side], hole[t:t + side, l:l + side]
    x = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), (512, 512), interpolation=cv2.INTER_AREA)
    mm = (cv2.resize(m.astype(np.float32), (512, 512), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
    out = sess.run(None, {"image": x.transpose(2, 0, 1)[None].astype(np.float32),
                          "mask": mm[None, None]})[0][0].transpose(1, 2, 0)
    out = out / 255 if out.max() > 2 else out
    out = cv2.resize(cv2.cvtColor(np.clip(out, 0, 1).astype(np.float32), cv2.COLOR_RGB2BGR), crop.shape[1::-1],
                     interpolation=cv2.INTER_CUBIC)
    res = img.copy()
    res[t:t + side, l:l + side][m] = out[m]
    return res


def _plate(img: np.ndarray, hole: np.ndarray, how: str, o: Options) -> np.ndarray:
    """The still with the moving regions' area filled, so what shows behind a moved strand is background."""
    if not hole.any():
        return img
    if how == "lama" and LAMA.exists():
        return _lama(img, hole)
    if how == "lama":
        _say(o, f"plate: no LaMa model at {LAMA}, using OpenCV Telea instead")
    u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return cv2.inpaint(u8, hole.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA).astype(np.float32) / 255


class _Encoder:
    def __init__(self, path: Path, w: int, h: int, fps: int, gop: int):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                                   "-r", str(fps), "-i", "-", "-c:v", "ffv1", "-level", "3", "-g", str(gop),
                                   "-pix_fmt", "bgr0", str(path)], stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        self.p.stdin.write(frame.tobytes())

    def close(self) -> None:
        self.p.stdin.close()
        if self.p.wait():
            raise RuntimeError(f"ffmpeg failed ({self.p.returncode})")


def _finish(out: Path, fps: int, frames: int) -> None:
    enc = h264_encoder()
    quality = ["-crf", "18"] if enc == "libx264" else ["-b:v", "10M"]
    run = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)  # noqa: E731
    run("-i", str(out / "master.mkv"), "-c:v", enc, *quality, "-g", str(frames), "-pix_fmt", "yuv420p",
        "-r", str(fps), str(out / "loop.mp4"))
    run("-stream_loop", "2", "-i", str(out / "loop.mp4"), "-c", "copy", str(out / "preview3x.mp4"))


def render(o: Options) -> Path:
    t0 = time.time()
    o.still = Path(o.still)
    W, H = map(int, o.size.split("x"))
    N = max(1, round(o.seconds * o.fps))
    out = Path(o.out) if o.out else Path("design-data/loops") / o.still.stem / (o.preset or f"rain-{o.rain}")
    out.mkdir(parents=True, exist_ok=True)

    src = cv2.imread(str(o.still))
    still = cover(src, W, H).astype(np.float32) / 255
    matte_raw = _fit_mask(load_or_make_matte(o.still, o.matte_model or DEFAULT_MATTE, o.redo_matte), W, H)
    matte = feather(matte_raw, 2)
    has_char = bool((matte >= 0.5).any())
    still_dc = decontaminate(still, matte) if has_char else still

    regions = {k: _fit_mask(v, W, H) for k, v in load_regions(o.still).items()} if has_char else {}
    face = (regions.pop("face", np.zeros((H, W), np.float32)) >= 0.5).astype(np.float32)  # resizing leaves faint edges
    wanted = set(o.motion.split(",")) if o.motion and not o.still_character else set()
    # Grow each moving region by its outline (SAM 2 stops just inside the ink line), so the line moves with the cloth.
    moving = {k: np.minimum(cv2.dilate(v, np.ones((7, 7), np.uint8)), matte) * (1 - face)
              for k, v in regions.items() if k in wanted and (v >= 0.5).any()}
    taken: set[int] = set()
    rain_far = Rain((W, H), N, o.rain, o.seed)
    wind = (-1.0 if rain_far.slant > 0 else 1.0, 0.0)  # drops drift left as they fall, so the wind blows left
    motion = Motion(moving, face, (W, H), N, o.seconds, wind, o.seed, taken,
                    breath=0.004 if "breath" in wanted else 0.0) if moving else None
    if wanted and not moving and has_char:
        _say(o, "motion: no hair/coat masks beside the still (python -m tools.loop_still.regions), so she holds still")

    # A moved edge can only uncover the strip of its region within its largest move of the region's edge; only that
    # strip (and 3 px past the edge) is filled, so LaMa works from nearby context instead of inventing a whole coat.
    union = np.zeros((H, W), np.float32)
    hole = np.zeros((H, W), bool)
    for r in (motion.regions.values() if motion else []):
        union = np.maximum(union, r.mask)
        inside = (r.mask >= 0.05).astype(np.uint8)
        strip = cv2.distanceTransform(inside, cv2.DIST_L2, 3) <= r.reach + 3
        hole |= (cv2.dilate(inside, np.ones((7, 7), np.uint8)) > 0) & strip
    hole &= ~(face > 0)
    plate = _plate(still_dc, hole, o.plate, o) if motion else still_dc
    body = matte * (1 - union)  # the character that never moves

    lights = None
    if o.lights:
        lights = Lights((np.clip(plate, 0, 1) * 255).astype(np.uint8), o.size, o.seconds, o.fps, o.seed, o.strength,
                        (matte * 255).astype(np.uint8), o.train, o.floor, o.passes, o.sweeps, o.sign_blink)
    rain_near = Rain((W, H), N, o.rain, o.seed, near=True) if o.near_rain else None
    fog = Fog((W, H), N, o.seed) if o.fog else None
    splashes = Splashes((W, H), N, o.ground, o.seed, o.splashes if o.rain != "none" else 0, avoid=matte)

    blinks = None
    if o.blink is not False and has_char:
        blinks = load_blinks(o.still, N, o.fps, o.seed, fit=lambda im: cover(im, W, H))
        if blinks is None and o.blink:
            _say(o, "blink: no eye patches beside the still (<still>.blink-half.png, .blink-closed.png; they are drawn "
                    "with tools/fix_area.py on the 4U box), so no blinks")

    held = "matte core" if o.still_character else "face"
    held_mask = (cv2.erode((matte >= 0.5).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0).astype(np.float32) \
        if o.still_character else face
    reach = max((r.reach for r in motion.regions.values()), default=0) if motion else 0
    swept = cv2.dilate((union >= 0.05).astype(np.uint8), np.ones((2 * int(reach) + 7,) * 2, np.uint8)) if motion else None
    checks = Checks(still_dc, held_mask, matte if has_char else np.zeros_like(matte), N, o.fps,
                    blinks.mask if blinks else None, ring_skip=swept)
    rim = ((matte >= 0.5) & (cv2.distanceTransform((matte >= 0.5).astype(np.uint8), cv2.DIST_L2, 3) <= 3)) \
        .astype(np.float32)[..., None] if o.edge_tint and has_char and lights else None

    sha = hashlib.sha1()
    enc = None if o.frames_only else _Encoder(out / "master.mkv", W, H, o.fps, N)
    for i in range(o.frames_only or N):
        city = lights.frame(i) if lights else plate.copy()
        city = city + rain_far.layer(i)[..., None] * RAIN_TINT
        if fog:
            city = city + fog.layer(i)[..., None]
        frame = city * (1 - body[..., None]) + still_dc * body[..., None]
        if motion:
            for moved, alpha in motion.layers(still_dc, i):
                frame = frame * (1 - alpha[..., None]) + moved * alpha[..., None]
            checks.stretch(*motion.stretch(i))
        if blinks:
            frame = blinks.apply(frame, i)
        checks.character(i, frame)
        if rim is not None:
            glow = cv2.GaussianBlur(np.clip(city - plate, 0, None), (0, 0), 6)
            frame = frame + 0.35 * rim * glow
        checks.back(i, frame)
        frame = frame + splashes.layer(i)[..., None] * SPLASH_TINT
        if rain_near:
            frame = frame + rain_near.layer(i)[..., None] * RAIN_TINT
        u8 = (np.clip(frame, 0, 1) * 255).round().astype(np.uint8)
        sha.update(u8.tobytes())
        if o.frames_only:
            cv2.imwrite(str(out / f"{i:04d}.png"), u8)
            continue
        checks.final(i, u8.astype(np.float32) / 255)
        enc.write(u8)
        if i == 0:
            cv2.imwrite(str(out / "poster.jpg"), u8, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if i % 120 == 0:
            print(f"frame {i}/{N}", flush=True)
    if o.frames_only:
        return out
    enc.close()
    _finish(out, o.fps, N)
    opts = {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(o).items() if k != "log"}
    meta = {"options": opts, "frames": N, "held": held, "matte_model": str(o.matte_model or DEFAULT_MATTE),
            "cycles": motion.cycles if motion else {}, "blinks": [s for s, _ in blinks.schedule] if blinks else [],
            "checks": checks.result(), "frames_sha1": sha.hexdigest(), "notes": o.log,
            "seconds_taken": round(time.time() - t0, 1)}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return out
