"""Redraw one area of an image and leave every other pixel exactly as it was.

    python -m tools.fix_area IMAGE --shape X,Y X,Y X,Y... --prompt "what belongs there" --out FIXED.png
        [--fill R,G,B] [--denoise 0.4] [--seed N]

The crop gives the model context, Differential Diffusion fades the redraw out towards the mask's edge, and the
result goes back through the same mask. A light redraw keeps the colours underneath, so changing what something
is (skin to cloth) needs --fill, a rough coat of the new colour for the redraw to work from. It refuses to save if anything outside the mask moved, and writes
FIXED-compare.jpg, before beside after, for review.
"""

import argparse
import asyncio
import io
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from narrator.comfyui_backend import ComfyUIBackend
from narrator.design_sheets import _TILED, NEGATIVE, QUALITY, SCENE_MOOD, STYLE, candidate_workflow

CONTEXT = 2.0  # crop side as a multiple of the area, so the redraw can see what it has to match
MIN_CROP = 256
SAMPLE_SIDE = 1024
FEATHER_RATIO = 0.08
COMFY_URL = "http://192.168.10.19:8188"


def crop_around(size: tuple[int, int], region: tuple[int, int, int, int], min_crop: int = MIN_CROP) -> tuple[int, int, int, int]:
    width, height = size
    x0, y0, x1, y1 = region
    side = min(max(int(max(x1 - x0, y1 - y0) * CONTEXT), min_crop), width, height)
    left = max(0, min(width - side, (x0 + x1) // 2 - side // 2))
    top = max(0, min(height - side, (y0 + y1) // 2 - side // 2))
    return left, top, left + side, top + side


def bounds(shape: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs, ys = zip(*shape)
    return min(xs), min(ys), max(xs), max(ys)


def soft_mask(size: tuple[int, int], shape: list[tuple[int, int]], feather: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(shape, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(feather))


def rough_fill(im: Image.Image, mask: Image.Image, colour: tuple[int, int, int]) -> Image.Image:
    return Image.composite(Image.new("RGB", im.size, colour), im, mask)


def stitch(scene: bytes, repaint: bytes, crop: tuple[int, int, int, int], shape: list[tuple[int, int]],
           feather: int) -> tuple[bytes, Image.Image]:
    im = Image.open(io.BytesIO(scene)).convert("RGB")
    mask = soft_mask(im.size, shape, feather)
    side = crop[2] - crop[0]
    layer = im.copy()
    layer.paste(Image.open(io.BytesIO(repaint)).convert("RGB").resize((side, side), Image.LANCZOS), crop[:2])
    out = io.BytesIO()
    Image.composite(layer, im, mask).save(out, "PNG")
    return out.getvalue(), mask


def changed_outside(before: bytes, after: bytes, mask: Image.Image) -> int:
    """Pixels that differ where the mask is fully off. A clean fix scores zero."""
    diff = ImageChops.difference(Image.open(io.BytesIO(before)).convert("RGB"), Image.open(io.BytesIO(after)).convert("RGB"))
    r, g, b = diff.split()
    any_change = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v else 0)
    outside = mask.point(lambda v: 255 if v == 0 else 0)
    moved = ImageChops.multiply(any_change, outside)
    return moved.histogram()[255]


def fix_workflow(positive: str, negative: str, seed: int, crop: str, mask: str, denoise: float) -> dict:
    wf = candidate_workflow(positive, negative, seed, cfg=3.5)
    del wf["5"]
    wf["60"] = {"class_type": "LoadImage", "inputs": {"image": crop}}
    wf["61"] = {"class_type": "VAEEncodeTiled", "inputs": {"pixels": ["60", 0], "vae": ["4", 2], **_TILED}}
    wf["62"] = {"class_type": "LoadImageMask", "inputs": {"image": mask, "channel": "red"}}
    wf["63"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["61", 0], "mask": ["62", 0]}}
    wf["64"] = {"class_type": "DifferentialDiffusion", "inputs": {"model": wf["3"]["inputs"]["model"]}}
    wf["3"]["inputs"].update(model=["64", 0], latent_image=["63", 0], denoise=denoise)
    return wf


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def compare(before: bytes, after: bytes, crop: tuple[int, int, int, int], path: Path) -> None:
    a, b = (Image.open(io.BytesIO(x)).convert("RGB").crop(crop).resize((900, 900), Image.LANCZOS) for x in (before, after))
    sheet = Image.new("RGB", (1800, 900))
    sheet.paste(a, (0, 0))
    sheet.paste(b, (900, 0))
    sheet.save(path, quality=90)


async def fix(scene: bytes, shape: list[tuple[int, int]], positive: str, negative: str, seed: int, denoise: float, backend,
              fill: tuple[int, int, int] | None = None, min_crop: int = MIN_CROP) -> tuple[bytes, tuple[int, int, int, int]]:
    im = Image.open(io.BytesIO(scene)).convert("RGB")
    region = bounds(shape)
    crop = crop_around(im.size, region, min_crop)
    feather = max(2, int((region[2] - region[0] + region[3] - region[1]) / 2 * FEATHER_RATIO))
    scale = SAMPLE_SIDE / (crop[2] - crop[0])
    local = [(int((x - crop[0]) * scale), int((y - crop[1]) * scale)) for x, y in shape]
    local_mask = soft_mask((SAMPLE_SIDE, SAMPLE_SIDE), local, int(feather * scale))
    enlarged = im.crop(crop).resize((SAMPLE_SIDE, SAMPLE_SIDE), Image.LANCZOS)
    if fill:
        enlarged = rough_fill(enlarged, local_mask, fill)
    crop_name = await backend.upload_image("nightwire_fix_crop.png", _png(enlarged))
    mask_name = await backend.upload_image("nightwire_fix_mask.png", _png(local_mask.convert("RGB")))
    repaint = await backend.run_workflow(fix_workflow(positive, negative, seed, crop_name, mask_name, denoise))
    after, mask = stitch(scene, repaint, crop, shape, feather)
    moved = changed_outside(scene, after, mask)
    if moved:
        raise RuntimeError(f"{moved} pixels moved outside the mask")
    return after, crop


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path)
    parser.add_argument("--shape", required=True, nargs="+", help="polygon corners as X,Y in the image's own pixels")
    parser.add_argument("--fill", help="R,G,B rough coat under the redraw, for changing what the area is")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--denoise", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=90233)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-crop", type=int, default=MIN_CROP, help="smallest crop side: wider shows the model more of the room")
    parser.add_argument("--comfy-url", default=COMFY_URL)
    args = parser.parse_args(argv)
    shape = [tuple(int(v) for v in point.split(",")) for point in args.shape]
    fill = tuple(int(v) for v in args.fill.split(",")) if args.fill else None
    positive = ", ".join((QUALITY, STYLE, args.prompt, SCENE_MOOD))
    negative = ", ".join(x for x in (NEGATIVE, args.negative) if x)
    scene = args.image.read_bytes()
    after, crop = asyncio.run(fix(scene, shape, positive, negative, args.seed, args.denoise, ComfyUIBackend(args.comfy_url), fill, args.min_crop))
    args.out.write_bytes(after)
    compare(scene, after, crop, args.out.with_name(args.out.stem + "-compare.jpg"))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
