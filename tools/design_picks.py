"""Saves the owner's design picks from the LAN gallery page. Standard library only,
so it runs in a bare python container next to the dashboard.

    python design_picks.py --data picks.json --designs <gallery dir> [--port 8766]

GET    /designs/api/picks         -> {slug: {action, n, round, note, at}}
PUT    /designs/api/picks/<slug>  {"action": "pick", "n": 2, "round": 1}
                                  {"action": "reroll", "note": "older"} | {"action": "skip"}
DELETE /designs/api/picks/<slug>  undo

GET    /designs/api/reviews         -> {slug: {verdict, note, v, at}}
PUT    /designs/api/reviews/<slug>  {"verdict": "ok", "v": "<sheet version>"} | {"verdict": "fix", "note": "...", "v": "..."}
DELETE /designs/api/reviews/<slug>  undo

GET    /designs/api/images         -> {image id: {verdict, note, at}}
PUT    /designs/api/images/<id>    {"verdict": "keep"} | {"verdict": "reject"} | {"verdict": "fix", "note": "..."}
DELETE /designs/api/images/<id>    undo

GET    /designs/api/renders -> latest Nightwire images in ComfyUI's history, with their recipes
GET    /designs/api/batch   -> the long batch in progress, with time left
PUT    /designs/api/batch   {"name": "Sheets", "done": 3, "total": 19, "item": "hachi", "failed": 0}
DELETE /designs/api/batch   clear it

There's no login: like the rest of the dashboard it relies on being LAN/Tailscale only. Requiring
a JSON content type stops other websites writing through the owner's browser.
"""

import argparse
import datetime as dt
import json
import os
import tempfile
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PREFIX = "/designs/api/picks"
REVIEWS = "/designs/api/reviews"
IMAGES = "/designs/api/images"
RENDERS = "/designs/api/renders"
BATCH = "/designs/api/batch"
MAX_BODY = 4096
MAX_NOTE = 500
RENDER_LIMIT = 12
HISTORY_SCAN = 120
NAME_MATCH = 0.5  # share of a character's tags a prompt must contain before it's named
# Only these may be listed or viewed, so nothing else ComfyUI has made shows on the dashboard.
# nginx's /svc/comfy/view applies the same rule to the images themselves.
_IMAGE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")
_VIEWABLE = re.compile(r"^(nightwire_|image_studio)[A-Za-z0-9_-]+\.png$")


class BadPick(ValueError):
    pass


def validate(slug: str, body, designs_dir: Path) -> dict:
    """The record to store, or BadPick. A pick must name an image the gallery really shows."""
    rounds = json.loads((designs_dir / "rounds.json").read_text())
    if slug not in rounds:
        raise BadPick("unknown design")
    if not isinstance(body, dict):
        raise BadPick("expected an object")
    action = body.get("action")
    if action == "pick":
        n, round_no = body.get("n"), body.get("round")
        if type(n) is not int or round_no != rounds[slug]:
            raise BadPick("that round is no longer current")
        if not (designs_dir / "img" / slug / f"r{round_no}-c{n}.jpg").is_file():
            raise BadPick("no such candidate")
        return {"action": action, "n": n, "round": round_no, "note": ""}
    if action == "reroll":
        note = body.get("note")
        if not isinstance(note, str) or not note.strip() or len(note) > MAX_NOTE:
            raise BadPick(f"a reroll needs a note of up to {MAX_NOTE} characters")
        return {"action": action, "n": 0, "round": 0, "note": note.strip()}
    if action == "skip":
        return {"action": action, "n": 0, "round": 0, "note": ""}
    raise BadPick("unknown action")


def validate_review(slug: str, body, designs_dir: Path) -> dict:
    """The owner's verdict on a rendered sheet. `v` ties it to one render, so a re-render asks again."""
    if slug not in json.loads((designs_dir / "status.json").read_text())["review"]:  # not rounds.json: that only lists designs in the picker
        raise BadPick("unknown design")
    if not isinstance(body, dict):
        raise BadPick("expected an object")
    verdict, note, v = body.get("verdict"), body.get("note", ""), body.get("v")
    if not isinstance(v, str) or not 0 < len(v) <= 40:
        raise BadPick("missing sheet version")
    if verdict == "ok":
        return {"verdict": verdict, "note": "", "v": v}
    if verdict == "fix" and isinstance(note, str) and note.strip() and len(note) <= MAX_NOTE:
        return {"verdict": verdict, "note": note.strip(), "v": v}
    raise BadPick(f"a fix needs a note of up to {MAX_NOTE} characters")


def validate_image(image: str, body, designs_dir: Path) -> dict:
    """The owner's verdict on one image in a gallery. A new render gets a new id, so it asks again."""
    if not _IMAGE_ID.fullmatch(image):
        raise BadPick("bad image id")
    if not isinstance(body, dict):
        raise BadPick("expected an object")
    verdict, note = body.get("verdict"), body.get("note", "")
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise BadPick(f"a note can be up to {MAX_NOTE} characters")
    if verdict not in ("keep", "fix", "reject"):
        raise BadPick("unknown verdict")
    if verdict == "fix" and not note.strip():
        raise BadPick("a fix needs a note")
    return {"verdict": verdict, "note": note.strip()}


def _style_of(positive: str) -> str:
    if "anime screenshot" in positive:
        return "Neon screenshot"
    if "bright face" in positive:
        return "Glossy cel"
    if "neon rim light" in positive:
        return "Neon rim sheet"
    return "Other"


def _character_in(positive: str, characters: dict) -> str:
    words = {w.strip() for w in positive.split(",")}
    best, best_score = "", NAME_MATCH
    for c in characters.values():
        tags = c.get("tags") or []
        score = sum(t in words for t in tags) / len(tags) if tags else 0
        if score > best_score:
            best, best_score = c.get("name", ""), score
    return best


def summarize_history(history: dict, characters: dict, limit: int = RENDER_LIMIT) -> list[dict]:
    """Newest first. ComfyUI lists its history oldest first."""
    out = []
    for entry in reversed(list(history.values())):
        images = [i for node in (entry.get("outputs") or {}).values() for i in node.get("images", [])
                  if i.get("type") == "output" and _VIEWABLE.match(i.get("subfolder", "") + i.get("filename", ""))]
        try:
            graph = entry["prompt"][2]
            sampler = next(n["inputs"] for n in graph.values() if n["class_type"] == "KSampler")
            positive = graph[sampler["positive"][0]]["inputs"]["text"]
            negative = graph[sampler["negative"][0]]["inputs"]["text"]
        except (KeyError, IndexError, TypeError, StopIteration):
            continue
        node = lambda kind, field: next((n["inputs"].get(field) for n in graph.values() if n["class_type"] == kind), None)
        for image in images:
            sub = image.get("subfolder", "")
            named = re.sub(r"_\d+_?\.png$", "", image["filename"]).replace("-", " ").title() if sub else ""
            out.append({"file": image["filename"], "subfolder": sub, "style": _style_of(positive),
                        "character": named or _character_in(positive, characters), "positive": positive,
                        "negative": negative, "seed": sampler.get("seed"), "steps": sampler.get("steps"),
                        "cfg": sampler.get("cfg"), "sampler": sampler.get("sampler_name"),
                        "checkpoint": node("CheckpointLoaderSimple", "ckpt_name"), "lora": node("LoraLoader", "lora_name")})
            if len(out) >= limit:
                return out
    return out


def next_batch(current: dict, body, now: float) -> dict:
    """The new batch record, or BadPick. Going backwards or changing name is a new batch, so the clock restarts."""
    if not isinstance(body, dict):
        raise BadPick("expected an object")
    name, done, total, item, failed = (body.get("name"), body.get("done"), body.get("total"),
                                       body.get("item", ""), body.get("failed", 0))
    if not isinstance(name, str) or not 0 < len(name) <= 80 or not isinstance(item, str) or len(item) > 80:
        raise BadPick("bad name or item")
    if type(done) is not int or type(total) is not int or type(failed) is not int or not 0 <= done <= total or total < 1 or failed < 0:
        raise BadPick("bad counts")
    same = current.get("name") == name and current.get("total") == total and current.get("done", 0) <= done
    return {"name": name, "done": done, "total": total, "item": item, "failed": failed,
            "started": current["started"] if same else int(now), "updated": int(now)}


def batch_view(state: dict, now: float) -> dict:
    """What the dashboard shows. Time per step comes from the steps finished so far."""
    if not state:
        return {}
    elapsed = state["updated"] - state["started"]
    left = state["total"] - state["done"]
    eta = round(elapsed / state["done"] * left) if state["done"] and left else None
    return {**state, "eta_seconds": eta, "elapsed_seconds": elapsed, "age_seconds": int(now) - state["updated"]}


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


class Store:
    """picks.json, replaced atomically. Unreadable data raises rather than reading as empty, so a
    damaged file can't be silently overwritten and lose the owner's picks."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def read(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def change(self, slug: str, record: dict | None) -> dict:
        with self.lock:
            picks = self.read()
            if record is None:
                picks.pop(slug, None)
            else:
                picks[slug] = {**record, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
            write_json_atomic(self.path, picks)
            return picks


def make_server(host: str, port: int, data: Path, designs_dir: Path,
                comfyui: str = "http://127.0.0.1:8188") -> ThreadingHTTPServer:
    data = Path(data)
    batch_file = data.with_name("batch.json")
    batch_lock = threading.Lock()
    routes = {PREFIX: (Store(data), validate), REVIEWS: (Store(data.with_name("reviews.json")), validate_review),
              IMAGES: (Store(data.with_name("images.json")), validate_image)}
    designs_dir = Path(designs_dir)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload) -> None:
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _route(self):
            """(store, validator, slug) for a /<slug> path, or None."""
            path = self.path.split("?", 1)[0]
            for prefix, (store, check) in routes.items():
                if path.startswith(prefix + "/"):
                    return store, check, path[len(prefix) + 1:]
            return None

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == RENDERS:
                return self._renders()
            if path == BATCH:
                try:
                    state = json.loads(batch_file.read_text()) if batch_file.exists() else {}
                    return self._send(200, batch_view(state, time.time()))
                except (OSError, ValueError) as e:
                    return self._send(500, {"error": f"batch file unreadable: {e}"})
            route = routes.get(path)
            if route is None:
                return self._send(404, {"error": "not found"})
            try:
                self._send(200, route[0].read())
            except (OSError, ValueError) as e:
                self._send(500, {"error": f"picks file unreadable: {e}"})

        def _renders(self):
            try:
                with urllib.request.urlopen(f"{comfyui}/history?max_items={HISTORY_SCAN}", timeout=8) as r:
                    history = json.load(r)
            except (OSError, ValueError) as e:
                return self._send(502, {"error": f"ComfyUI unavailable: {e}"})
            try:
                characters = json.loads((designs_dir / "characters.json").read_text())
            except (OSError, ValueError):
                characters = {}
            self._send(200, summarize_history(history, characters))

        def do_PUT(self):
            is_batch = self.path.split("?", 1)[0] == BATCH
            route = None if is_batch else self._route()
            if route is None and not is_batch:
                return self._send(404, {"error": "not found"})
            store, check, slug = route or (None, None, None)
            self.close_connection = True  # any refused body stays unread
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
                if is_batch:
                    with batch_lock:
                        current = json.loads(batch_file.read_text()) if batch_file.exists() else {}
                        state = next_batch(current, body, time.time())
                        write_json_atomic(batch_file, state)
                    return self._send(200, batch_view(state, time.time()))
                record = check(slug, body, designs_dir)
            except OSError as e:
                return self._send(500, {"error": f"couldn't save: {e}"})
            except BadPick as e:
                return self._send(400, {"error": str(e)})
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad JSON"})
            self._write(store, slug, record)

        def do_DELETE(self):
            if self.path.split("?", 1)[0] == BATCH:
                with batch_lock:
                    batch_file.unlink(missing_ok=True)
                return self._send(200, {})
            route = self._route()
            if route is None:
                return self._send(404, {"error": "not found"})
            self._write(route[0], route[2], None)

        def _write(self, store: Store, slug: str, record: dict | None) -> None:
            try:
                self._send(200, store.change(slug, record))
            except (OSError, ValueError) as e:
                self._send(500, {"error": f"couldn't save: {e}"})

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--designs", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    make_server(args.host, args.port, args.data, args.designs).serve_forever()
