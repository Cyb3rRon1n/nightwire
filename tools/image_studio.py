"""Image Studio backend: pick an approved character and/or location, say what's happening, render
on ComfyUI in the approved look. Standard library only, so it runs in a bare python container.

    python -m tools.image_studio --state jobs.json [--comfy URL] [--ollama URL] [--port 8767]

GET    /studio/api/options            what the form can offer
GET    /studio/api/jobs               recent jobs, refreshed from ComfyUI
POST   /studio/api/jobs               {character, location, shot, size, action, seed, day, count}
DELETE /studio/api/jobs/<id>          cancel a queued job, or drop a finished one from the gallery
GET    /studio/api/image/<id>         the rendered PNG

docs/art-direction.md is enforced here rather than in the page: only approved designs, no raw
prompts or custom negatives, and the action text can't ask for nudity, sexual content or minors.
There's no login: like the rest of the dashboard it relies on being LAN/Tailscale only.
"""

import argparse
import datetime as dt
import json
import random
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from narrator.design_sheets import CHARACTER_NEGATIVE_EXTRA
from narrator.designs import load_designs
from narrator.image_prompt import _below_chest
from tools.design_picks import write_json_atomic
from tools.imagegen import SIZES, build

PREFIX = "/studio/api"
MAX_BODY = 8192
MAX_ACTION = 500
MAX_COUNT = 4
MAX_PENDING = 12   # keeps a stuck tab or double-click from filling the GPU's whole evening
KEEP_JOBS = 200    # gallery records only; the PNGs stay in ComfyUI's output folder
MAX_SEED = 2**32 - 1
PENDING = ("queued", "rendering")

SHOTS = {
    "scene": {"label": "In a scene", "kind": "subject", "size": "base", "bust": False},
    "portrait": {"label": "Portrait", "kind": "portrait", "size": "portrait", "bust": True},
    "closeup": {"label": "Moody closeup", "kind": "closeup", "size": "portrait", "bust": True},
    "sheet": {"label": "Model sheet", "kind": "character", "size": "base", "bust": False},
}
SIZE_LABELS = {"base": "Landscape, fast", "portrait": "Portrait, fast", "square": "Square 2K", "1080p": "1080p wallpaper",
               "1440p": "1440p wallpaper", "4k": "4K wallpaper", "ultrawide": "Ultrawide wallpaper", "phone": "Phone wallpaper"}
assert set(SIZE_LABELS) == set(SIZES)

# Best effort: spellings can dodge a word list, so the negatives below are always applied too.
REFUSED = re.compile(
    r"\b(nude|nudes|nudity|naked|nsfw|explicit|uncensored|topless|bottomless|undress\w*|nipples?|areolae?|breasts? out|"
    r"pussy|vagina|penis|genitals?|sex|sexual|sexually|intercourse|cum|orgasm|porn|porno|hentai|ahegao|"
    r"loli|lolita|shota|child|children|kid|kids|teen|teens|teenage|teenager|underage|minor|minors|"
    r"schoolgirl|schoolboy|little girl|little boy|young girl|young boy|toddler|infant)\b", re.I)


class BadRequest(ValueError):
    pass


class Busy(BadRequest):
    pass


def refused_terms(text: str) -> list[str]:
    plain = " ".join(re.sub(r"[^a-z]+", " ", text.lower()).split())   # beats nude_body, (nude:1.4)
    return sorted({m.group(0) for m in REFUSED.finditer(plain)})


def _subject(d) -> str:
    return "1other" if "android" in d.tags else {"feminine": "1girl", "masculine": "1boy"}.get(d.presentation, "1other")


def compose(body: dict, designs: dict, rng=random) -> list[dict]:
    """One render spec per image, or BadRequest. Nothing from the request reaches the prompt
    except the screened action text; everything else is looked up from approved designs."""
    if not isinstance(body, dict):
        raise BadRequest("expected an object")

    def approved(field, kind):
        slug = body.get(field) or None
        if slug is None:
            return None
        d = designs.get(slug) if isinstance(slug, str) else None
        if d is None or d.kind != kind or d.status != "approved":
            raise BadRequest(f"{field} isn't an approved {kind}")
        return d

    character, location = approved("character", "character"), approved("location", "location")
    if not character and not location:
        raise BadRequest("choose a character or a location")
    shot = body.get("shot", "scene")
    if shot not in SHOTS:
        raise BadRequest("unknown shot")
    if not character:
        shot = "scene"
    size = body.get("size") or SHOTS[shot]["size"]
    if size not in SIZES:
        raise BadRequest("unknown size")
    action = body.get("action", "")
    if not isinstance(action, str) or len(action) > MAX_ACTION:
        raise BadRequest(f"the description can be up to {MAX_ACTION} characters")
    action = " ".join(action.split())
    bad = refused_terms(action)
    if bad:
        raise BadRequest(f"Image Studio keeps everyone adult and clothed, so it won't use: {', '.join(bad)}")
    count = body.get("count", 1)
    if type(count) is not int or not 1 <= count <= MAX_COUNT:
        raise BadRequest(f"count must be 1 to {MAX_COUNT}")
    seed = body.get("seed")
    if seed == "design":
        seed = (character or location).seed
    elif seed is None:
        seed = rng.randint(1, MAX_SEED - MAX_COUNT)
    elif type(seed) is not int or not 1 <= seed <= MAX_SEED - MAX_COUNT:
        raise BadRequest("seed must be a positive whole number")
    day = body.get("day", False)
    if type(day) is not bool:
        raise BadRequest("day must be true or false")

    spec = SHOTS[shot]
    parts = []
    if character:
        tags = [t.strip() for t in character.tags.split(",")]
        # The record's required details always go in; carried items stay out of close framings, where they float.
        tags = [t for t in tags if t not in character.required and not (spec["bust"] and (_below_chest(t) or t in character.held))]
        parts.append(", ".join([*character.required, *tags]))
    if location and shot in ("scene",):
        parts.append(location.tags)
    if action:
        parts.append(action)
    prompt = ", ".join(parts)
    negative = ", ".join(x for x in (character.negative if character else "", location.negative if location and not character else "",
                                     CHARACTER_NEGATIVE_EXTRA) if x)
    label = " at ".join(d.name for d in (character, location if shot == "scene" else None) if d)
    return [{
        "character": character.slug if character else None, "location": location.slug if location and shot == "scene" else None,
        "label": label, "shot": shot, "size": size, "action": action, "day": day, "seed": seed + i,
        "prompt": prompt, "negative": negative,
        "kind": spec["kind"] if character else "scene",
        "subject": _subject(character) if character else "",
        "prefix": f"image_studio/{(character or location).slug}",
    } for i in range(count)]


def workflow(spec: dict) -> dict:
    wf = build(spec["prompt"], spec["kind"], False, spec["negative"], spec["size"], spec["seed"],
               day=spec["day"], subject=spec["subject"])
    wf["9"]["inputs"]["filename_prefix"] = spec["prefix"]
    return wf


class Comfy:
    """The few ComfyUI and Ollama calls the studio needs."""

    def __init__(self, comfy_url: str, ollama_url: str):
        self.comfy, self.ollama = comfy_url.rstrip("/"), ollama_url.rstrip("/")

    def _json(self, url: str, body=None, timeout=15):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        return json.loads(raw) if raw else None

    def submit(self, wf: dict) -> str:
        return self._json(f"{self.comfy}/prompt", {"prompt": wf})["prompt_id"]

    def queue(self) -> dict:
        return self._json(f"{self.comfy}/queue")

    def history(self, prompt_id: str) -> dict | None:
        return self._json(f"{self.comfy}/history/{prompt_id}").get(prompt_id)

    def cancel(self, prompt_id: str) -> None:
        self._json(f"{self.comfy}/queue", {"delete": [prompt_id]})

    def image(self, image: dict) -> bytes:
        query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""),
                                        "type": image.get("type", "output")})
        with urllib.request.urlopen(f"{self.comfy}/view?{query}", timeout=60) as r:
            return r.read()

    def free_ollama(self) -> None:
        for model in self._json(f"{self.ollama}/api/ps").get("models", []):
            self._json(f"{self.ollama}/api/generate", {"model": model["name"], "keep_alive": 0}, timeout=30)

    def free_comfy(self) -> None:
        self._json(f"{self.comfy}/free", {"unload_models": True, "free_memory": True})


class Studio:
    def __init__(self, state: Path, comfy, designs=load_designs, now=None):
        self.state, self.comfy, self.designs = Path(state), comfy, designs
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        self.lock = threading.Lock()

    def _read(self) -> list[dict]:
        # Unreadable data raises instead of reading as empty, so it can't be overwritten.
        return json.loads(self.state.read_text()) if self.state.exists() else []

    def _write(self, jobs: list[dict]) -> None:
        write_json_atomic(self.state, jobs[-KEEP_JOBS:])

    def options(self) -> dict:
        approved = [d for d in self.designs().values() if d.status == "approved"]

        def entries(kind):
            found = []
            for d in sorted((d for d in approved if d.kind == kind), key=lambda d: d.name):
                role = next((n.split("draft:", 1)[1].strip() for n in d.notes if "draft:" in n), "")
                found.append({"slug": d.slug, "name": d.name, "role": "" if role.startswith("from world") else role})
            return found

        return {"characters": entries("character"), "locations": entries("location"),
                "shots": [{"id": k, "label": v["label"], "size": v["size"]} for k, v in SHOTS.items()],
                "sizes": [{"id": k, "label": v} for k, v in SIZE_LABELS.items()],
                "maxCount": MAX_COUNT, "maxAction": MAX_ACTION}

    def create(self, body) -> list[dict]:
        specs = compose(body, self.designs())
        with self.lock:
            jobs = self._read()
            if sum(j["status"] in PENDING for j in jobs) + len(specs) > MAX_PENDING:
                raise Busy(f"up to {MAX_PENDING} images can wait at once; let some finish first")
            try:
                self.comfy.free_ollama()
            except OSError:
                pass   # best effort: a model left loaded slows the render, it doesn't stop it
            created = []
            try:
                for spec in specs:
                    comfy_id = self.comfy.submit(workflow(spec))
                    public = {k: spec[k] for k in ("character", "location", "label", "shot", "size", "action", "day", "seed")}
                    created.append({**public, "id": uuid.uuid4().hex, "comfy_id": comfy_id, "status": "queued",
                                    "created": self.now(), "image": None, "error": ""})
            finally:
                if created:
                    self._write(jobs + created)   # whatever ComfyUI accepted stays tracked
            return created

    def refresh(self) -> dict:
        with self.lock:
            jobs = self._read()
            pending = [j for j in jobs if j["status"] in PENDING]
            queue = self.comfy.queue()
            running = {q[1] for q in queue["queue_running"]}
            waiting = [q[1] for q in sorted(queue["queue_pending"], key=lambda q: q[0])]
            changed = False
            for j in pending:
                entry = self.comfy.history(j["comfy_id"])
                status, position, error, image = j["status"], None, "", None
                if entry and entry.get("status", {}).get("completed"):
                    images = entry.get("outputs", {}).get("9", {}).get("images", [])
                    status = "done" if images else "failed"
                    image = images[0] if images else None
                    error = "" if images else "ComfyUI finished without an image"
                elif entry and entry.get("status", {}).get("status_str") == "error":
                    status, error = "failed", "ComfyUI hit an error on this image"
                elif j["comfy_id"] in running:
                    status = "rendering"
                elif j["comfy_id"] in waiting:
                    status, position = "queued", len(running) + waiting.index(j["comfy_id"])
                else:
                    status, error = "failed", "ComfyUI lost this job, probably a restart. Try again."
                if (status, error, image) != (j["status"], j["error"], j["image"]):
                    changed = True
                j.update(status=status, error=error, image=image)
                j["position"] = position
            if changed:
                self._write(jobs)
            if pending and not any(j["status"] in PENDING for j in jobs) and not (running or waiting):
                try:
                    self.comfy.free_comfy()   # hand the GPU back so the narrator's model can load
                except OSError:
                    pass
            visible = [{k: v for k, v in j.items() if k not in ("comfy_id", "image")} | {"hasImage": bool(j["image"])}
                       for j in reversed(jobs)]
            return {"jobs": visible[:60], "othersWaiting": len(set(running) | set(waiting)) - sum(j["status"] in PENDING for j in jobs)}

    def delete(self, job_id: str) -> None:
        with self.lock:
            jobs = self._read()
            job = next((j for j in jobs if j["id"] == job_id), None)
            if job is None:
                raise KeyError(job_id)
            if job["status"] == "rendering":
                raise BadRequest("it's already rendering, so it can't be cancelled")
            if job["status"] == "queued":
                self.comfy.cancel(job["comfy_id"])
            self._write([j for j in jobs if j["id"] != job_id])

    def image(self, job_id: str) -> bytes:
        with self.lock:
            job = next((j for j in self._read() if j["id"] == job_id), None)
        if job is None or not job["image"]:
            raise KeyError(job_id)
        return self.comfy.image(job["image"])


def make_server(host: str, port: int, studio: Studio) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload) -> None:
            raw = json.dumps(payload).encode()
            self._bytes(status, raw, "application/json", "no-store")

        def _bytes(self, status: int, raw: bytes, ctype: str, cache: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _guarded(self, fn) -> None:
            try:
                fn()
            except KeyError:
                self._send(404, {"error": "not found"})
            except Busy as e:
                self._send(429, {"error": str(e)})
            except BadRequest as e:
                self._send(400, {"error": str(e)})
            except OSError as e:   # ComfyUI down, disk trouble
                self._send(502, {"error": f"ComfyUI or the disk didn't answer: {e}"})
            except ValueError as e:
                self._send(500, {"error": f"jobs file unreadable: {e}"})

        def _path(self) -> str:
            return self.path.split("?", 1)[0]

        def do_GET(self):
            path = self._path()
            if path == f"{PREFIX}/options":
                self._guarded(lambda: self._send(200, studio.options()))
            elif path == f"{PREFIX}/jobs":
                self._guarded(lambda: self._send(200, studio.refresh()))
            elif path.startswith(f"{PREFIX}/image/"):
                job_id = path.rsplit("/", 1)[1]
                self._guarded(lambda: self._bytes(200, studio.image(job_id), "image/png", "private, max-age=86400"))
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self._path() != f"{PREFIX}/jobs":
                return self._send(404, {"error": "not found"})
            self.close_connection = True   # any refused body stays unread
            # Requiring JSON stops other websites posting through the owner's browser.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": "expected JSON"})
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return self._send(400, {"error": "bad length"})
            if not 0 <= length <= MAX_BODY:
                return self._send(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad JSON"})
            self._guarded(lambda: self._send(201, {"created": len(studio.create(body))}))

        def do_DELETE(self):
            path = self._path()
            if not path.startswith(f"{PREFIX}/jobs/"):
                return self._send(404, {"error": "not found"})
            job_id = path.rsplit("/", 1)[1]
            self._guarded(lambda: (studio.delete(job_id), self._send(200, {}))[1])

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--comfy", default="http://127.0.0.1:8188")
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    make_server(args.host, args.port, Studio(args.state, Comfy(args.comfy, args.ollama))).serve_forever()
