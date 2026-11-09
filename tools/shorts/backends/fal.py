"""fal.ai queue API: POST the input, poll status, fetch the result, download the video.

Endpoint ids and field names verified on fal.ai model API pages on 2026-11-08 (https://fal.ai/models/<endpoint>/api):
  bytedance/seedance-2.5/reference-to-video, bytedance/seedance-2.0/reference-to-video,
  bytedance/seedance-2.0/fast/reference-to-video, fal-ai/kling-video/o3/pro/reference-to-video.
Result JSON: {"video": {"url": ...}} on all of them. generate_audio defaults to true (Seedance, Veo).
Prices (fal model pages, 2026-11-08, 720p): Seedance 2.5 $0.473/s, 2.0 $0.3024/s, 2.0 fast $0.2419/s (about 0.6x with a
reference video); Kling O3 pro $0.14/s. Image limits: Seedance 2.0 takes 9 images, 2.5 takes 30. fal advises against
large data: URIs, so images go as JPEGs of at most MAX_SIDE px.
Not included: veo-3.1-fast (fal-ai/veo3.1/fast/reference-to-video is slated for removal 2026-11-17, durations unclear).
"""

import base64
import io
import mimetypes
import time
from pathlib import Path

import httpx

from tools.shorts.takes import Ledger, estimate, file_take

QUEUE = "https://queue.fal.run"
# "duration_str": fal's duration is a string enum ("5"), not an int. Default (absent) = int.
MODELS = {
    "seedance-2.0-fast": {"endpoint": "bytedance/seedance-2.0/fast/reference-to-video", "prompt": "prompt", "images": "image_urls",
                          "video": "video_urls", "duration": "duration", "duration_str": True, "min_s": 4, "extra": {"resolution": "720p"}},
    "seedance-2.0": {"endpoint": "bytedance/seedance-2.0/reference-to-video", "prompt": "prompt", "images": "image_urls",
                     "video": "video_urls", "duration": "duration", "duration_str": True, "min_s": 4, "extra": {"resolution": "720p"}},
    "seedance-2.5": {"endpoint": "bytedance/seedance-2.5/reference-to-video", "prompt": "prompt", "images": "image_urls",
                     "video": "video_urls", "duration": "duration", "duration_str": True, "min_s": 4, "extra": {"resolution": "720p"}},
    # "skip": refs a model can't take (image limits); left out with a note. Kling has no top-level reference-video field (only elements[].video_url), so video=None.
    "kling-3": {"endpoint": "fal-ai/kling-video/o3/pro/reference-to-video", "prompt": "prompt", "images": "image_urls",
                "video": None, "duration": "duration", "duration_str": True, "min_s": 3, "extra": {},
                # Kling takes at most 7 images; Rin's deck is already on her turnaround.
                "skip": ("C2_props.png",)},
}


def load_key(path: Path = Path.home() / ".config" / "nightwire" / "secrets.env") -> str:
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"FAL_KEY missing in {path}; the owner adds it (FAL_KEY=...)")


MAX_SIDE, JPEG_QUALITY = 2048, 90  # the sheets are 3-9 MB PNGs; full size would make a ~60 MB request


def data_uri(path: Path) -> str:
    """Images go as a JPEG no longer than MAX_SIDE on either side; other files go as they are."""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if not mime.startswith("image/"):
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_input(model: str, prompt: str, refs: list[tuple[str, Path]], seconds: float) -> dict:
    spec = MODELS[model]
    secs = int(round(seconds))
    body = {spec["prompt"]: prompt, spec["duration"]: str(secs) if spec.get("duration_str") else secs, **spec["extra"]}
    dropped = [label for label, _ in refs if not label.endswith(".png") and not (label.endswith(".mp4") and spec["video"])]
    if dropped:
        raise ValueError(f"{model} cannot send these refs: {dropped}")
    images = [data_uri(p) for label, p in refs if label.endswith(".png")]
    videos = [data_uri(p) for label, p in refs if label.endswith(".mp4")]
    if images:
        body[spec["images"]] = images
    if videos and spec["video"]:
        body[spec["video"]] = videos
    return body


def start(model, prompt, refs, seconds, *, key: str, client: httpx.Client) -> dict:
    """POST the job (this is the paid step); returns the queue job dict."""
    return client.post(f"{QUEUE}/{MODELS[model]['endpoint']}", json=build_input(model, prompt, refs, seconds),
                       headers={"Authorization": f"Key {key}"}, timeout=120).raise_for_status().json()


def fetch(job: dict, *, key: str, client: httpx.Client, poll_s: float = 5.0, timeout_s: float = 900) -> bytes:
    headers = {"Authorization": f"Key {key}"}
    deadline = time.monotonic() + timeout_s
    while client.get(job["status_url"], headers=headers, timeout=30).raise_for_status().json()["status"] != "COMPLETED":
        if time.monotonic() > deadline:
            raise TimeoutError(f"fal request {job['request_id']} not done after {timeout_s}s")
        time.sleep(poll_s)
    result = client.get(job["response_url"], headers=headers, timeout=60).raise_for_status().json()
    return client.get(result["video"]["url"], timeout=300).raise_for_status().content


def submit(model, prompt, refs, seconds, *, key: str, client: httpx.Client, poll_s: float = 5.0,
           timeout_s: float = 900) -> bytes:
    job = start(model, prompt, refs, seconds, key=key, client=client)
    return fetch(job, key=key, client=client, poll_s=poll_s, timeout_s=timeout_s)


def run_take(short_dir: Path, shot_id: str, model: str, prompt: str, refs, seconds: float, budget: float, *,
             key: str, client: httpx.Client) -> str:
    seconds = int(round(seconds))  # fal bills and receives whole seconds
    if seconds < MODELS[model]["min_s"]:
        raise ValueError(f"{model} needs at least {MODELS[model]['min_s']}s, got {seconds}")
    ledger, cost = Ledger(short_dir / "costs.json"), estimate(model, seconds)
    ledger.check(budget, cost)
    job = start(model, prompt, refs, seconds, key=key, client=client)
    ledger.add(shot_id, f"req-{job['request_id']}", model, cost)  # money is spent once the POST succeeds
    video = fetch(job, key=key, client=client)
    tmp = short_dir / "shots" / shot_id / "incoming.mp4"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(video)
    tid = file_take(short_dir / "shots" / shot_id, tmp, {"model": model, "cost": cost, "backend": "fal", "seconds": seconds,
                                                          "request_id": job["request_id"], "refs": [label for label, _ in refs]})
    tmp.unlink()
    return tid
