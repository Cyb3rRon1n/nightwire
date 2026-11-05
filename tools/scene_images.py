"""Pixel helpers for solo scenes."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FACE_PAD = 2.2


def square_on_blur(im: Image.Image, side: int = 1024) -> bytes:
    """The whole figure on a square, so IP-Adapter's centre crop keeps head and shoes. The bars are the image itself, blurred."""
    bg = im.resize((side, side)).filter(ImageFilter.GaussianBlur(40))
    scale = side / max(im.size)
    fg = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    bg.paste(fg, ((side - fg.width) // 2, (side - fg.height) // 2))
    out = io.BytesIO()
    bg.save(out, "PNG")
    return out.getvalue()


def face_box(png: bytes) -> tuple[int, int, int, int] | None:
    """A square around the largest head, or None."""
    from imgutils.detect import detect_heads
    im = Image.open(io.BytesIO(png)).convert("RGB")
    heads = detect_heads(im)
    if not heads:
        return None
    x0, y0, x1, y1 = max(heads, key=lambda h: (h[0][2] - h[0][0]) * (h[0][3] - h[0][1]))[0]
    side = min(int(max(x1 - x0, y1 - y0) * FACE_PAD), *im.size)
    left = max(0, min(im.width - side, (x0 + x1) // 2 - side // 2))
    top = max(0, min(im.height - side, (y0 + y1) // 2 - side // 2))
    return left, top, left + side, top + side


def paste_face(scene: bytes, face: bytes, box: tuple[int, int, int, int]) -> bytes:
    """Back into the scene with a feathered oval, shifted to the crop's average colour so the scene's light survives."""
    im = Image.open(io.BytesIO(scene)).convert("RGB")
    side = box[2] - box[0]
    new = np.asarray(Image.open(io.BytesIO(face)).convert("RGB").resize((side, side), Image.LANCZOS)).astype(float)
    old = np.asarray(im.crop(box)).astype(float)
    new = np.clip(new + old.mean(axis=(0, 1)) - new.mean(axis=(0, 1)), 0, 255).astype("uint8")
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse((side * .1, side * .1, side * .9, side * .9), fill=255)
    im.paste(Image.fromarray(new), box[:2], mask.filter(ImageFilter.GaussianBlur(side * .06)))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()
