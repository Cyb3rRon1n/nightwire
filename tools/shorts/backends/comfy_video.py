"""Local video takes on the 4U box's ComfyUI: looping backgrounds from an approved still (plan 2026-11-23-4u-local-loop-tests).

Each model is one ComfyUI workflow exported in API format to workflows/<name>.json, with its nodes titled
start, end (optional), prompt, length and seed. A take is free, so nothing here touches the ledger.
"""

import json
import math
import subprocess
import time
import urllib.error
from pathlib import Path

from tools.shorts.takes import file_take

WORKFLOWS = Path(__file__).parent / "workflows"
MODELS = {
    "wan22-flf": {"fps": 16, "frame_step": 4, "workflow": "wan22-flf.json"},
    "anisora-v3": {"fps": 16, "frame_step": 4, "workflow": "anisora-v3.json"},  # Wan 2.1 based
    "ltx23": {"fps": 24, "frame_step": 8, "workflow": "ltx23.json"},
}
NEEDED = ("start", "prompt", "length", "seed")
# The input each titled node carries, by the names the node types use for it.
INPUTS = {"start": ("image",), "end": ("image",), "prompt": ("text", "positive_prompt", "prompt"),
          "length": ("length", "num_frames", "frame_count"), "seed": ("seed", "noise_seed")}
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")


def frames(model: str, seconds: float) -> int:
    """At least `seconds` of video, rounded up to the model's step*n+1 frame rule (Wan 4n+1, LTX 8n+1)."""
    m = MODELS[model]
    step = m["frame_step"]
    return step * math.ceil((math.ceil(seconds * m["fps"]) - 1) / step) + 1


def titled(g: dict, title: str) -> dict | None:
    return next((n for n in g.values() if n.get("_meta", {}).get("title") == title), None)


def _set(node: dict, title: str, value) -> None:
    key = next((k for k in INPUTS[title] if k in node["inputs"]), None)
    if key is None:
        raise ValueError(f"node titled {title!r} ({node.get('class_type')}) has none of the inputs {INPUTS[title]}")
    node["inputs"][key] = value


def graph_from(path: Path, model: str, start: str, end: str | None, prompt: str, seconds: float, seed: int) -> dict:
    g = json.loads(Path(path).read_text())
    missing = [t for t in NEEDED if titled(g, t) is None]
    if missing:
        raise ValueError(f"{Path(path).name}: no node titled {', '.join(missing)}")
    if end is not None and titled(g, "end") is None:
        raise ValueError(f"{model} has no end frame input in {Path(path).name}; run it without a loop")
    _set(titled(g, "start"), "start", start)
    if titled(g, "end") is not None:
        _set(titled(g, "end"), "end", end or start)  # a workflow that has an end frame always needs one
    _set(titled(g, "prompt"), "prompt", prompt)
    _set(titled(g, "length"), "length", frames(model, seconds))
    _set(titled(g, "seed"), "seed", seed)
    return g


def graph(model: str, start: str, end: str | None, prompt: str, seconds: float, seed: int) -> dict:
    return graph_from(WORKFLOWS / MODELS[model]["workflow"], model, start, end, prompt, seconds, seed)
