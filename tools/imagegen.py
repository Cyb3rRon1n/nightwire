"""Ad-hoc image generation in Nightwire's approved look (docs/art-direction.md).

    python -m tools.imagegen "rainy rooftop bar, neon signs, skyline" --size 4k
    python -m tools.imagegen "1girl, ..." --kind character --size phone --seed 42 --count 3
    python -m tools.imagegen "anything" --raw            # your prompt exactly, no style added

Writes PNGs plus the ComfyUI workflow JSON (load it in ComfyUI's UI to tweak) to
design-data/imagegen/. Sizes: base renders at an SDXL bucket, then refine + AnimeSharp
upscale, then a final resize to the exact wallpaper size.
"""

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

from narrator.comfyui_backend import ComfyUIBackend
from narrator.design_sheets import CHARACTER_MATURE, CHARACTER_SHEET_STYLE, candidate_workflow, sheet_workflow
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE

# name: (target width, height, base width, base height, high_res)
SIZES = {
    "base": (1216, 832, 1216, 832, False),
    "1080p": (1920, 1080, 1344, 768, True),
    "1440p": (2560, 1440, 1344, 768, True),
    "4k": (3840, 2160, 1344, 768, True),
    "ultrawide": (3440, 1440, 1536, 640, True),
    "phone": (1080, 2340, 640, 1536, True),
    "square": (2048, 2048, 1024, 1024, True),
}
CHARACTER_NEGATIVE = ("nude, nipples, pussy, penis, sex, explicit, loli, shota, child, petite, flat chest, young, "
                      "teenage, aged down, chibi, kawaii, moe, cute, deformed")


def build(prompt: str, kind: str, raw: bool, negative: str, size: str, seed: int) -> dict:
    if raw:
        pos, neg = prompt, negative or NEGATIVE
    elif kind == "character":
        q = QUALITY.replace("safe", "sensitive")
        pos = ", ".join([q, CHARACTER_SHEET_STYLE, CHARACTER_MATURE, prompt])
        neg = ", ".join(x for x in (NEGATIVE, CHARACTER_NEGATIVE, negative) if x)
    else:
        pos = ", ".join([QUALITY, STYLE, "scenery, no humans" if kind == "scene" else "", prompt]).replace(", ,", ",")
        neg = ", ".join(x for x in (NEGATIVE, negative) if x)
    w, h, bw, bh, high_res = SIZES[size]
    wf = sheet_workflow(pos, neg, seed) if high_res else candidate_workflow(pos, neg, seed)
    wf["5"]["inputs"].update(width=bw, height=bh)
    if high_res:
        wf["41"] = {"class_type": "ImageScale", "inputs": {"image": ["40", 0], "upscale_method": "lanczos",
                                                           "width": w, "height": h, "crop": "center"}}
        wf["9"]["inputs"]["images"] = ["41", 0]
    wf["9"]["inputs"]["filename_prefix"] = "nightwire_imagegen"
    return wf


async def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.imagegen")
    p.add_argument("prompt")
    p.add_argument("--kind", choices=("scene", "character", "plain"), default="scene",
                   help="scene: game style, no people; character: mature character style; plain: game style, no subject")
    p.add_argument("--size", choices=sorted(SIZES), default="base")
    p.add_argument("--negative", default="")
    p.add_argument("--raw", action="store_true", help="send the prompt exactly, no style or quality tags")
    p.add_argument("--seed", type=int)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--out", type=Path, default=Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "imagegen")
    p.add_argument("--comfyui-url", default=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"))
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    backend = ComfyUIBackend(base_url=a.comfyui_url, profile="noobai", timeout=900.0)
    for i in range(a.count):
        seed = (a.seed + i) if a.seed is not None else random.randint(1, 2**32 - 1)
        wf = build(a.prompt, a.kind, a.raw, a.negative, a.size, seed)
        stem = f"{a.kind}-{a.size}-{seed}"
        (a.out / f"{stem}.workflow.json").write_text(json.dumps(wf, indent=1))
        (a.out / f"{stem}.png").write_bytes(await backend.run_workflow(wf))
        print(a.out / f"{stem}.png", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
