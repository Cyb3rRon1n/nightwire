"""Consistency test: do approved characters still look like themselves in other locations and with each other?

    python -m tools.design_scenes solo [--characters a b] [--locations x y]
    python -m tools.design_scenes pairs

Writes design-data/scenes/<character>--<location>.png and pair--<a>--<b>--<location>.png. Skips files that exist.
Two people in one prompt blend, so a pair gets one prompt per side of the frame using ComfyUI's built-in area
conditioning. Check results with `~/.cache/nightwire-qa/bin/python -m tools.design_check --scenes`.
"""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from narrator.comfyui_backend import ComfyUIBackend
from narrator.designs import load_designs
from tools.batch_status import Batch, batch_url
from tools.design_studio import _gpu_etiquette
from tools.image_studio import _subject, compose, workflow
from tools.imagegen import build

CHARACTERS = ("ayame-tsuda", "akira-sendo", "rin-kageyama", "mitsu", "daichi-tanabe", "mei-lan")
LOCATIONS = ("the-loop", "mama-satos-izakaya", "kuroshio-docks")
PAIRS = (("ayame-tsuda", "shinji-okubo", "mama-satos-izakaya"), ("akira-sendo", "yuki-shirasagi", "kuroshio-docks"),
         ("mitsu", "kaede-mori", "the-loop"), ("daichi-tanabe", "goro-bessho", "kuroshio-docks"))
# The sides overlap a little so the two people share one scene rather than two pasted halves.
LEFT, RIGHT = (0.0, 0.56), (0.44, 1.0)


def solo_jobs(designs, characters, locations):
    for c in characters:
        for loc in locations:
            spec = compose({"character": c, "location": loc, "shot": "scene", "seed": "design",
                            "action": "standing, looking at viewer, cowboy shot, solo"}, designs)[0]
            yield f"{c}--{loc}.png", workflow(spec)


def _region_tags(d) -> str:
    return ", ".join(dict.fromkeys([*d.required, *(t.strip() for t in d.tags.split(",") if t.strip() not in d.held)]))


def _crowd(a, b) -> str:
    subjects = sorted("1boy" if _subject(d) == "1boy" else "1girl" for d in (a, b))
    return {"1boy,1boy": "2boys", "1girl,1girl": "2girls"}.get(",".join(subjects), "1boy, 1girl")


def pair_workflow(a, b, location, seed: int) -> dict:
    """The scene in the shared prompt, and each character limited to their own side of the frame."""
    negative = ", ".join(x for x in (a.negative, b.negative, "solo, merged bodies, fused faces, extra arms") if x)
    wf = build(f"{_crowd(a, b)}, side by side, two people, cowboy shot, {location.tags}", "scene", False, negative, "base", seed)
    width, height = wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]
    clip = wf["6"]["inputs"]["clip"]
    combined = ["6", 0]
    for i, (d, (start, end)) in enumerate(((a, LEFT), (b, RIGHT))):
        text = build(_region_tags(d), "subject", False, negative, "base", seed, subject=_subject(d))["6"]["inputs"]["text"]
        x, w = int(width * start) // 8 * 8, int(width * (end - start)) // 8 * 8
        base = 50 + i * 3
        wf[str(base)] = {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": clip}}
        wf[str(base + 1)] = {"class_type": "ConditioningSetArea", "inputs": {"conditioning": [str(base), 0], "width": w,
                             "height": height, "x": x, "y": 0, "strength": 1.2}}
        wf[str(base + 2)] = {"class_type": "ConditioningCombine", "inputs": {"conditioning_1": combined, "conditioning_2": [str(base + 1), 0]}}
        combined = [str(base + 2), 0]
    wf["3"]["inputs"]["positive"] = combined
    wf["9"]["inputs"]["filename_prefix"] = "nightwire_design/pair"
    return wf


def pair_jobs(designs, pairs=PAIRS):
    for a, b, loc in pairs:
        yield f"pair--{a}--{b}--{loc}.png", pair_workflow(designs[a], designs[b], designs[loc], designs[a].seed)


def gpu_busy(url: str) -> bool:
    with urllib.request.urlopen(f"{url.rstrip('/')}/queue", timeout=10) as r:
        q = json.load(r)
    return bool(q["queue_running"] or q["queue_pending"])


async def render(jobs, out: Path, backend, batch_to: str | None = None) -> int:
    failed = 0
    out.mkdir(parents=True, exist_ok=True)
    todo = [(name, wf) for name, wf in jobs if not (out / name).exists()]
    batch = Batch("Scene test", len(todo), batch_to) if todo else None
    for name, wf in todo:
        try:
            (out / name).write_bytes(await backend.run_workflow(wf))
            print(name, flush=True)
            batch.step(name)
        except Exception as e:  # one bad render shouldn't lose the rest of a long batch
            print(f"{name}: {e}", file=sys.stderr, flush=True)
            failed += 1
            batch.step(name, failed=True)
    return failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("solo", "pairs"))
    parser.add_argument("--characters", nargs="*", default=CHARACTERS)
    parser.add_argument("--locations", nargs="*", default=LOCATIONS)
    parser.add_argument("--designs-dir", type=Path, default=Path("narrator/worlds/designs"))
    parser.add_argument("--design-dir", type=Path, default=Path("design-data"))
    parser.add_argument("--comfyui-url", default=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"))
    args = parser.parse_args(argv)
    if gpu_busy(args.comfyui_url):
        print("ComfyUI is busy; wait for the current batch to finish.", file=sys.stderr)
        return 1
    designs = load_designs(args.designs_dir)
    jobs = solo_jobs(designs, args.characters, args.locations) if args.mode == "solo" else pair_jobs(designs)
    _gpu_etiquette(args.comfyui_url, before=True)
    try:
        backend = ComfyUIBackend(base_url=args.comfyui_url, profile="noobai", timeout=600.0)
        return 1 if asyncio.run(render(jobs, args.design_dir / "scenes", backend, batch_url())) else 0
    finally:
        _gpu_etiquette(args.comfyui_url, before=False)


if __name__ == "__main__":
    raise SystemExit(main())
