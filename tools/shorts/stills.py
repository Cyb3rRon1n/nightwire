"""A free local opening-frame still per shot (the storyboard frame the owner approves with the shot).
Two characters use design_scenes' left/right area prompts so they don't blend; one character uses imagegen's
subject workflow. Night look only (the house style string already says night)."""

import asyncio
import re

from tools.design_scenes import _region_tags, pair_workflow
from tools.image_studio import _subject
from tools.imagegen import build

SIZE_WORDS = {"ECU": "extreme close-up, face focus", "CU": "close-up, portrait", "MCU": "upper body",
              "MS": "cowboy shot", "MWS": "cowboy shot, wide", "WS": "full body, wide shot", "EWS": "very wide shot, scenery"}
SIDE = re.compile(r"screen[- ]?(left|right)", re.IGNORECASE)


def in_frame_order(shot) -> list[str]:
    def key(cid):
        m = SIDE.search(shot.frame[cid])
        return {"left": 0, "right": 2}.get(m.group(1).lower(), 1) if m else 1
    return sorted(shot.frame, key=key)


def still_workflow(short, shot, designs, seed: int) -> dict:
    who = [short.cast[c] for c in in_frame_order(shot)]
    place = designs[short.place]
    words = f"{SIZE_WORDS.get(shot.size, '')}, {shot.angle}, night"
    if len(who) >= 2:
        wf = pair_workflow(designs[who[0]], designs[who[1]], place, seed)
    else:
        d = designs[who[0]]
        wf = build(f"{_region_tags(d)}, {place.tags}", "subject", False, d.negative or "", "base", seed, subject=_subject(d))
    wf["6"]["inputs"]["text"] = f"{words}, " + wf["6"]["inputs"]["text"]
    wf["9"]["inputs"]["filename_prefix"] = f"nightwire_shorts/{short.slug}-{shot.id}"
    return wf


async def render(jobs, backend) -> list[str]:
    """jobs: [(path, workflow)]. Returns error strings; one failure does not stop the rest."""
    errors = []
    for path, wf in jobs:
        try:
            path.write_bytes(await backend.run_workflow(wf))
            print(path, flush=True)
        except Exception as e:  # keep going: a long batch should not lose the other shots
            errors.append(f"{path.parent.name}: {e}")
    return errors


def run(jobs, url: str) -> list[str]:
    from narrator.comfyui_backend import ComfyUIBackend
    from tools.design_studio import _gpu_etiquette
    _gpu_etiquette(url, before=True)
    try:
        return asyncio.run(render(jobs, ComfyUIBackend(base_url=url, profile="noobai", timeout=600.0)))
    finally:
        _gpu_etiquette(url, before=False)
