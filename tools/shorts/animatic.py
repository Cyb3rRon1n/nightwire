"""Animatic: every scene's shots in order as a silent mp4 - boards held for the shot's duration, the camera move
mimicked, plate lights breathing (shots <= LIGHTS_MAX_S), a lower-third caption, 0.5 s black between scenes."""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.shorts import plates as plate_mod
from tools.shorts import remote
from tools.shorts.model import load_short
from tools.shorts.wall import board_file

LIGHTS_MAX_S = 10
GAP_S = 0.5
FADE_S = 1.0


def zoom_pan(move: str, p: float) -> tuple[float, float]:
    """(zoom, pan) at progress p in 0..1. push-in: zoom 1.00 -> 1.06 centred; pan: fixed 1.04 zoom drifting +-1.5% of width."""
    m = (move or "").lower()
    if "push" in m:
        return 1.0 + 0.06 * p, 0.0
    if "pan" in m:
        return 1.04, (p - 0.5) * 0.03
    return 1.0, 0.0


def _camera(im: Image.Image, zoom: float, pan: float) -> Image.Image:
    if zoom == 1.0 and pan == 0.0:
        return im
    w, h = im.size
    cw, ch = w / zoom, h / zoom
    x = (w - cw) / 2 + pan * w
    x = min(max(x, 0), w - cw)
    return im.resize((w, h), Image.BILINEAR, box=(x, (h - ch) / 2, x + cw, (h + ch) / 2))


def _caption(im: Image.Image, text: str) -> Image.Image:
    im = im.copy()
    w, h = im.size
    size = max(12, h // 32)
    band = Image.new("RGB", (w, size * 2 + 8), (0, 0, 0))
    im.paste(Image.blend(im.crop((0, h - band.height, w, h)), band, 0.65), (0, h - band.height))
    ImageDraw.Draw(im).text((size // 2, h - band.height + 4 + size // 2), text, fill=(240, 240, 244),
                            font=ImageFont.load_default(size=size))
    return im


def _fit(path: Path | None, size: tuple[int, int]) -> Image.Image:
    if path is None:
        return Image.new("RGB", size, (22, 22, 26))
    im = Image.open(path).convert("RGB")
    s = max(size[0] / im.width, size[1] / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - size[0]) // 2, (im.height - size[1]) // 2
    return im.crop((l, t, l + size[0], t + size[1]))


class _Lit:
    """Plate light breathing, one Lights object per plate image (rebuilt only when the plate changes)."""

    def __init__(self, size, fps):
        self.size, self.fps, self.cache = size, fps, {}

    def gain(self, plate: Path | None, i: int):
        if plate is None or not plate.exists():
            return None
        if plate not in self.cache:
            import cv2

            from tools.lights import Lights
            self.cache[plate] = Lights(cv2.imread(str(plate)), f"{self.size[0]}x{self.size[1]}", seconds=8, fps=self.fps)
        return self.cache[plate].gain(i)


def frames(film, shorts_dir: Path, design_dir: Path, fps: int = 24, size: tuple[int, int] = (1216, 832), lights: bool = True, plates_root: Path | None = None):
    """Yields RGB PIL frames: Σ round(duration*fps) per shot plus GAP_S black between scenes."""
    import numpy as np
    lit = _Lit(size, fps)
    for n, scene in enumerate(film.scenes):
        if n:
            for _ in range(round(GAP_S * fps)):
                yield Image.new("RGB", size)
        short = load_short(shorts_dir / scene)
        work = design_dir / "shorts" / scene
        catalogue = plate_mod.load_plates(short.place, plates_root)
        for sh in short.shots:
            start = _fit(board_file(work, sh.id), size)
            end_png = work / "shots" / sh.id / "board-end.png"
            end = _fit(end_png, size) if end_png.exists() and board_file(work, sh.id) != end_png else None
            plate = catalogue.get(sh.plate)
            ppath = plate_mod.plate_path(design_dir, short.place, plate) if plate else None
            use = lights and sh.duration <= LIGHTS_MAX_S
            text = f"{short.title} · {sh.id} · {sh.action or sh.summary}"
            n_fr = round(sh.duration * fps)
            for i in range(n_fr):
                t = i / fps
                im = start
                if end is not None and t > sh.duration - FADE_S:
                    im = Image.blend(start, end, min(1.0, (t - (sh.duration - FADE_S)) / FADE_S))
                g = lit.gain(ppath, i) if use else None
                if g is not None:
                    a = np.asarray(im, np.float32) * g
                    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
                yield _caption(_camera(im, *zoom_pan(sh.move, i / max(1, n_fr - 1))), text)


def build(film, film_slug: str, shorts_dir: Path, design_dir: Path, site_root: Path, fps: int = 24,
          size: tuple[int, int] = (1216, 832), plates_root: Path | None = None) -> Path:
    out = site_root / "films" / film_slug / "animatic.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = remote.h264_encoder()
    quality = ["-crf", "20"] if enc == "libx264" else ["-b:v", "4M"]
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
                           "-r", str(fps), "-i", "-", "-c:v", enc, "-pix_fmt", "yuv420p", *quality, str(out)], stdin=subprocess.PIPE)
    try:
        for fr in frames(film, shorts_dir, design_dir, fps, size, plates_root=plates_root):
            ff.stdin.write(fr.tobytes())
    finally:
        try:
            ff.stdin.close()
        except OSError:
            pass  # ffmpeg died; the original error is the one to surface
        ff.wait()
    if ff.returncode:
        raise RuntimeError(f"ffmpeg failed ({ff.returncode})")
    return out
