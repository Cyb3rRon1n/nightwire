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

There's no login: like the rest of the dashboard it relies on being LAN/Tailscale only. Requiring
a JSON content type stops other websites writing through the owner's browser.
"""

import argparse
import datetime as dt
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PREFIX = "/designs/api/picks"
REVIEWS = "/designs/api/reviews"
MAX_BODY = 4096
MAX_NOTE = 500


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
    if slug not in json.loads((designs_dir / "rounds.json").read_text()):
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


def make_server(host: str, port: int, data: Path, designs_dir: Path) -> ThreadingHTTPServer:
    data = Path(data)
    routes = {PREFIX: (Store(data), validate), REVIEWS: (Store(data.with_name("reviews.json")), validate_review)}
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
            route = routes.get(self.path.split("?", 1)[0])
            if route is None:
                return self._send(404, {"error": "not found"})
            try:
                self._send(200, route[0].read())
            except (OSError, ValueError) as e:
                self._send(500, {"error": f"picks file unreadable: {e}"})

        def do_PUT(self):
            route = self._route()
            if route is None:
                return self._send(404, {"error": "not found"})
            store, check, slug = route
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
                record = check(slug, json.loads(self.rfile.read(length)), designs_dir)
            except BadPick as e:
                return self._send(400, {"error": str(e)})
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad JSON"})
            self._write(store, slug, record)

        def do_DELETE(self):
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
