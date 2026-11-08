"""fal.ai queue API: POST the input, poll status, fetch the result, download the video.

Endpoint ids and field names verified on fal.ai model API pages on 2026-11-08 (https://fal.ai/models/<endpoint>/api):
  bytedance/seedance-2.5/reference-to-video, bytedance/seedance-2.0/reference-to-video,
  bytedance/seedance-2.0/fast/reference-to-video, fal-ai/kling-video/o3/pro/reference-to-video.
Result JSON: {"video": {"url": ...}} on all of them. generate_audio defaults to true (Seedance, Veo).
Prices (https://fal.ai/pricing): only Kling O3 pro ($0.14/s) confirmed; Seedance rates in takes.RATES are unconfirmed.
Not included: veo-3.1-fast (fal-ai/veo3.1/fast/reference-to-video is slated for removal 2026-11-17, durations unclear).
"""

import base64
import mimetypes
import time
from pathlib import Path

import httpx

from tools.shorts.takes import Ledger, estimate, file_take

QUEUE = "https://queue.fal.run"
# "duration_str": fal's duration is a string enum ("5"), not an int. Default (absent) = int.
MODELS = {
    "seedance-2.0-fast": {"endpoint": "bytedance/seedance-2.0/fast/reference-to-video", "prompt": "prompt", "images": "image_urls",
                          "video": "video_urls", "duration": "duration", "duration_str": True, "extra": {"resolution": "720p"}},
    "seedance-2.0": {"endpoint": "bytedance/seedance-2.0/reference-to-video", "prompt": "prompt", "images": "image_urls",
                     "video": "video_urls", "duration": "duration", "duration_str": True, "extra": {"resolution": "720p"}},
    "seedance-2.5": {"endpoint": "bytedance/seedance-2.5/reference-to-video", "prompt": "prompt", "images": "image_urls",
                     "video": "video_urls", "duration": "duration", "duration_str": True, "extra": {"resolution": "720p"}},
    # Kling has no top-level reference-video field (only elements[].video_url), so video=None.
    "kling-3": {"endpoint": "fal-ai/kling-video/o3/pro/reference-to-video", "prompt": "prompt", "images": "image_urls",
                "video": None, "duration": "duration", "duration_str": True, "extra": {}},
}


def load_key(path: Path = Path.home() / ".config" / "nightwire" / "secrets.env") -> str:
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"FAL_KEY missing in {path}; the owner adds it (FAL_KEY=...)")


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def build_input(model: str, prompt: str, refs: list[tuple[str, Path]], seconds: float) -> dict:
    spec = MODELS[model]
    secs = int(round(seconds))
    body = {spec["prompt"]: prompt, spec["duration"]: str(secs) if spec.get("duration_str") else secs, **spec["extra"]}
    images = [data_uri(p) for label, p in refs if label.endswith(".png")]
    videos = [data_uri(p) for label, p in refs if label.endswith(".mp4")]
    if images:
        body[spec["images"]] = images
    if videos and spec["video"]:
        body[spec["video"]] = videos
    return body


def submit(model, prompt, refs, seconds, *, key: str, client: httpx.Client, poll_s: float = 5.0,
           timeout_s: float = 900) -> bytes:
    headers = {"Authorization": f"Key {key}"}
    job = client.post(f"{QUEUE}/{MODELS[model]['endpoint']}", json=build_input(model, prompt, refs, seconds),
                      headers=headers, timeout=120).raise_for_status().json()
    deadline = time.monotonic() + timeout_s
    while client.get(job["status_url"], headers=headers, timeout=30).raise_for_status().json()["status"] != "COMPLETED":
        if time.monotonic() > deadline:
            raise TimeoutError(f"fal request {job['request_id']} not done after {timeout_s}s")
        time.sleep(poll_s)
    result = client.get(job["response_url"], headers=headers, timeout=60).raise_for_status().json()
    return client.get(result["video"]["url"], timeout=300).raise_for_status().content


def run_take(short_dir: Path, shot_id: str, model: str, prompt: str, refs, seconds: float, budget: float, *,
             key: str, client: httpx.Client) -> str:
    ledger, cost = Ledger(short_dir / "costs.json"), estimate(model, seconds)
    ledger.check(budget, cost)
    video = submit(model, prompt, refs, seconds, key=key, client=client)
    tmp = short_dir / "shots" / shot_id / "incoming.mp4"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(video)
    tid = file_take(short_dir / "shots" / shot_id, tmp, {"model": model, "cost": cost, "backend": "fal",
                                                          "seconds": seconds, "refs": [label for label, _ in refs]})
    tmp.unlink()
    ledger.add(shot_id, tid, model, cost)
    return tid
