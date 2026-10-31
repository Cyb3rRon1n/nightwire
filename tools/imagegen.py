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
import hashlib
import json
import os
import random
import sys
from pathlib import Path

from narrator.comfyui_backend import ComfyUIBackend
from narrator.design_sheets import (CHARACTER_MATURE, CHARACTER_NEGATIVE_EXTRA, CHARACTER_QUALITY,
                                    CHARACTER_SHEET_STYLE, CHECKPOINT, LORA, SHEET_NEGATIVE_EXTRA,
                                    candidate_workflow, sheet_workflow)
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE


SIZES = {
    "base": (1216, 832, 1216, 832, False),
    "1080p": (1920, 1080, 1344, 768, True),
    "1440p": (2560, 1440, 1344, 768, True),
    "4k": (3840, 2160, 1344, 768, True),
    "ultrawide": (3440, 1440, 1536, 640, True),
    "phone": (1080, 2340, 640, 1536, True),
    "square": (2048, 2048, 1024, 1024, True),
    "portrait": (832, 1216, 832, 1216, False),
}
# The approved look is hardcoded to night (narrator/image_prompt.STYLE). Daylight needs its own string:
# dropping "night" alone still leaves pink rim light and cyan backlight, which read as dusk.
DAY_STYLE = ("anime screenshot, anime coloring, cel shading, thick outlines, detailed background, "
             "daylight, clear sky, sunbeams, soft shadows, high contrast, depth of field, "
             "chromatic aberration, cyberpunk")
MATURE_18 = ("mature female, 25 years old, mature face, defined jawline, adult proportions, elegant, "
             "sophisticated")
MATURE_18_MALE = "mature male, 30 years old, mature face, defined jawline, adult proportions"
MATURE_18_OTHER = "adult, mature face, adult proportions"
MATURE_18_NEG = "child face, baby face, round face, youthful face, oversized eyes, small nose, loli face, underage"
TURNAROUND = ("character sheet, reference sheet, turnaround, multiple views, front view, from side, "
              "from behind, full body, standing")
KINDS = ("scene", "subject", "crowd", "portrait", "character", "plain")


def build(prompt: str, kind: str, raw: bool, negative: str, size: str, seed: int, *, day: bool = False,
          checkpoint: str | None = None, lora: str | None = None, lora_strength: float = 0.6,
          steps: int | None = None, cfg: float | None = None, sampler: str | None = None,
          scheduler: str | None = None, vpred: bool = True, clip_skip: int = -2, subject: str = "1girl",
          mature: bool = True, sheet_style: bool = False) -> dict:
    style = DAY_STYLE if day else STYLE
    adult = {"1girl": MATURE_18, "1boy": MATURE_18_MALE}.get(subject, MATURE_18_OTHER) if mature else ""
    if raw:
        pos, neg = prompt, negative or NEGATIVE
    elif kind == "portrait":
        pos = ", ".join([CHARACTER_QUALITY, subject, "solo, upper body, portrait, looking at viewer",
                         CHARACTER_SHEET_STYLE if sheet_style else style, adult, prompt])
        neg = ", ".join(x for x in (NEGATIVE, CHARACTER_NEGATIVE_EXTRA, MATURE_18_NEG if mature else "",
                                    "full body, feet, shoes, boots, legs, lower body",
                                    "scenery, background clutter" if sheet_style else "", negative) if x)
    elif kind == "character":
        pos = ", ".join([CHARACTER_QUALITY, CHARACTER_SHEET_STYLE, CHARACTER_MATURE, adult,
                         TURNAROUND, subject, prompt])
        neg = ", ".join(x for x in (NEGATIVE.replace(", text,", ","), SHEET_NEGATIVE_EXTRA, CHARACTER_NEGATIVE_EXTRA,
                                    MATURE_18_NEG if mature else "", negative) if x)
    elif kind == "subject":
        pos = ", ".join(x for x in (QUALITY, subject, style, adult, prompt) if x)
        neg = ", ".join(x for x in (NEGATIVE, CHARACTER_NEGATIVE_EXTRA, MATURE_18_NEG if mature else "", negative) if x)
    elif kind == "crowd":
        pos = ", ".join([QUALITY, style, "scenery, crowd, many people, from behind", prompt])
        neg = ", ".join(x for x in (NEGATIVE, negative) if x)
    else:
        pos = ", ".join([QUALITY, style, "scenery, no humans" if kind == "scene" else "", prompt]).replace(", ,", ",")
        neg = ", ".join(x for x in (NEGATIVE, negative) if x)
    w, h, bw, bh, high_res = SIZES[size]
    options = {"checkpoint": checkpoint or CHECKPOINT, "lora": LORA if lora is None else lora,
               "lora_strength": lora_strength, "steps": 28 if steps is None else steps,
               "cfg": 4.5 if cfg is None else cfg, "sampler": sampler or "euler",
               "scheduler": scheduler or "normal", "vpred": vpred, "clip_skip": clip_skip}
    wf = sheet_workflow(pos, neg, seed, **options) if high_res else candidate_workflow(pos, neg, seed, **options)
    wf["5"]["inputs"].update(width=bw, height=bh)
    if high_res:
        wf["41"] = {"class_type": "ImageScale", "inputs": {"image": ["40", 0], "upscale_method": "lanczos",
                                                           "width": w, "height": h, "crop": "center"}}
        wf["9"]["inputs"]["images"] = ["41", 0]
    wf["9"]["inputs"]["filename_prefix"] = "nightwire_imagegen"
    return wf


def design_defaults(slug: str) -> dict:
    from narrator.designs import load_designs
    d = load_designs()[slug]
    subject = "1other" if "android" in d.tags else {"feminine": "1girl", "masculine": "1boy"}.get(d.presentation, "1other")
    return {"prompt": d.tags, "negative": d.negative, "seed": d.seed, "subject": subject,
            "kind": "character" if d.kind == "character" else "scene"}


async def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.imagegen")
    p.add_argument("prompt", nargs="?", help="tags or description (omitted when using --design)")
    p.add_argument("--design", help="approved design slug: takes its tags, negative, seed and subject from "
                                    "narrator/worlds/designs/, so the render matches its Nightwire sheets")
    p.add_argument("--kind", choices=KINDS, default=None,
                   help="scene: game style, no people; subject: in-world scene with a person; crowd: in-world crowd; "
                        "portrait: in-world bust portrait; character: mature character sheet; plain: game style, no subject")
    p.add_argument("--size", choices=sorted(SIZES), default="base")
    p.add_argument("--day", action="store_true", help="daylight style instead of the default night look")
    p.add_argument("--negative", default="")
    p.add_argument("--raw", action="store_true", help="send the prompt exactly, no style or quality tags")
    p.add_argument("--subject", choices=("1girl", "1boy", "1other", ""),
                   help="subject-count tag for portrait/character/subject kinds (default 1girl; 1other for androids)")
    p.add_argument("--no-mature", dest="mature", action="store_false",
                   help="drop the 18+ adult face/proportion tags and negatives")
    p.add_argument("--sheet-style", action="store_true",
                   help="portrait kind only: use the design-studio sheet style (official art, flat light, plain "
                        "background) instead of the in-game anime-screenshot look")
    p.add_argument("--checkpoint", help=f"checkpoint filename (default {CHECKPOINT})")
    p.add_argument("--lora", help=f'LoRA filename, or "none" (default {LORA})')
    p.add_argument("--lora-strength", type=float, default=0.6)
    p.add_argument("--steps", type=int)
    p.add_argument("--cfg", type=float)
    p.add_argument("--sampler")
    p.add_argument("--scheduler")
    p.add_argument("--no-vpred", dest="vpred", action="store_false",
                   help="plain (non v-prediction) checkpoint: skips ModelSamplingDiscrete + RescaleCFG")
    p.add_argument("--clip-skip", type=int, default=-2)
    p.add_argument("--seed", type=int)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--out", type=Path, default=Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "imagegen")
    p.add_argument("--comfyui-url", default=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"))
    a = p.parse_args(argv)
    dd = design_defaults(a.design) if a.design else {}
    a.prompt = ", ".join(x for x in (dd.get("prompt"), a.prompt) if x)
    if not a.prompt:
        p.error("give a prompt or --design")
    a.kind = a.kind or dd.get("kind", "scene")
    a.negative = ", ".join(x for x in (dd.get("negative"), a.negative) if x)
    a.subject = a.subject if a.subject is not None else dd.get("subject", "1girl")
    if a.seed is None:
        a.seed = dd.get("seed")
    a.out.mkdir(parents=True, exist_ok=True)
    backend = ComfyUIBackend(base_url=a.comfyui_url, profile="noobai", timeout=900.0)
    for i in range(a.count):
        seed = (a.seed + i) if a.seed is not None else random.randint(1, 2**32 - 1)
        wf = build(a.prompt, a.kind, a.raw, a.negative, a.size, seed, day=a.day, checkpoint=a.checkpoint,
                   lora=a.lora, lora_strength=a.lora_strength, steps=a.steps, cfg=a.cfg, sampler=a.sampler,
                   scheduler=a.scheduler, vpred=a.vpred, clip_skip=a.clip_skip, subject=a.subject,
                   mature=a.mature, sheet_style=a.sheet_style)
        stem = (f"{a.kind}{'-day' if a.day else ''}{'-sheet' if a.sheet_style else ''}-{a.size}-{seed}"
                f"-{hashlib.sha1(a.prompt.encode()).hexdigest()[:6]}")
        (a.out / f"{stem}.workflow.json").write_text(json.dumps(wf, indent=1))
        (a.out / f"{stem}.png").write_bytes(await backend.run_workflow(wf))
        print(a.out / f"{stem}.png", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
