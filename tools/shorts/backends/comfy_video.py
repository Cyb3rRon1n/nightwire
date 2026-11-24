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


def seam(video: Path) -> float:
    """How far the last frame is from the first (mean absolute grey difference, 0-255): near 0 loops cleanly."""
    w, h = 64, 36
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    n = w * h
    if len(raw) < n:
        raise RuntimeError(f"{video.name}: no frames")
    first, last = raw[:n], raw[len(raw) - n:]
    return round(sum(abs(a - b) for a, b in zip(first, last)) / n, 2)


def _video(outputs: dict) -> dict | None:
    """The first video a run saved: VHS Video Combine reports it under "gifs", native SaveVideo under "videos"/"images"."""
    for node in outputs.values():
        for kind in ("gifs", "videos", "images"):
            for item in node.get(kind, []):
                if item.get("filename", "").lower().endswith(VIDEO_EXT):
                    return item
    return None


def _wait(comfy, pid: str, model: str, poll_s: float, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        h = comfy.history(pid)
        status = (h or {}).get("status", {})
        if status.get("status_str") == "error":
            err = next((m[1] for m in status.get("messages", []) if m[0] == "execution_error"), {})
            raise RuntimeError(f"{model}: node {err.get('node_type', '?')} ({err.get('node_id', '?')}) failed: "
                               f"{err.get('exception_message', 'unknown error').strip()}")
        if status.get("completed"):
            return h["outputs"]
        time.sleep(poll_s)
    raise RuntimeError(f"{model}: no result after {timeout_s:.0f}s (prompt {pid} may still be running in ComfyUI)")


def run_take(short_dir: Path, shot_id: str, model: str, prompt: str, still: Path, seconds: float, *, comfy,
             seed: int = 0, loop: bool = True, poll_s: float = 5.0, timeout_s: float = 1800) -> str:
    """Make one clip from the still (first and last frame when loop) and file it as a free take. Returns the take id."""
    still = Path(still)
    if not still.is_file():
        raise FileNotFoundError(f"still not found: {still}")
    url = getattr(comfy, "comfy", "ComfyUI")
    try:
        name = comfy.upload(still.name, still.read_bytes())
        g = graph(model, name, name if loop else None, prompt, seconds, seed)
        pid = comfy.submit(g)
        item = _video(_wait(comfy, pid, model, poll_s, timeout_s))
        if item is None:
            raise RuntimeError(f"{model}: the run saved no video (check the workflow's output node)")
        data = comfy.image(item)
    except urllib.error.URLError as e:
        raise RuntimeError(f"ComfyUI at {url} unreachable ({e.reason})") from e
    shot_dir = short_dir / "shots" / shot_id
    shot_dir.mkdir(parents=True, exist_ok=True)
    tmp = shot_dir / "incoming.mp4"
    tmp.write_bytes(data)
    try:
        tid = file_take(shot_dir, tmp, {"model": model, "backend": "comfy", "cost": 0, "seconds": seconds, "seed": seed,
                                        "loop": loop, "seam": seam(tmp), "still": still.name, "prompt": prompt})
    finally:
        tmp.unlink(missing_ok=True)
    return tid
