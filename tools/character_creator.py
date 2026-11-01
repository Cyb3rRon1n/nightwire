"""Character creator backend: players describe a character, see four candidates, redo until happy and
lock it in. The owner makes NPCs and AI characters the same way and approves players' suggestions.
Standard library only, so it runs in a bare python container. No photos: see the spec's build order.

Every character is a folder under <root>/characters/<private token>. One worker renders one image at a
time, and only when ComfyUI's queue is empty, so the owner's batches aren't starved or interleaved.
See docs/superpowers/specs/2026-11-01-character-creator-design.md.

    python -m tools.character_creator --root <state dir> [--comfy URL] [--ollama URL] [--port 8768]
    python -m tools.character_creator export <id> --state <dir> --designs-dir narrator/worlds/designs --design-dir design-data
"""

import argparse
import datetime as dt
import hmac
import json
import os
import random
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from narrator.design_sheets import (
    EXPRESSION_SIZE, EXPRESSIONS, candidate_prompt, candidate_workflow, expression_prompts, sheet_prompt, sheet_workflow,
)
from narrator.designs import save_design, validate
from tools.character_answers import QUESTIONS, clean_answers, clean_note, rated, to_design
from tools.design_picks import write_json_atomic
from tools.image_studio import MAX_SEED, BadRequest, Busy, Comfy

PREFIX = "/create/api"
MAX_BODY = 16 * 1024
KINDS = ("player", "npc", "ai")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{32}$")
NAME = re.compile(r"^(r\d+-c\d+-\d+|turnaround|colorguide|expression-\d)\.png$")
DENOISE = {"subtle": 0.35, "strong": 0.6}  # starting values; tune on real renders in Task 6
CANDIDATES_PER_ROUND = 4
MAX_WAITING = 12
MAX_DECLINE_NOTE = 500
ACTIVE = ("waiting", "rendering")
# The owner's batches leave about a second between images. Waiting this long for an empty queue keeps us out of those gaps.
QUIET_CHECKS = 3
QUIET_SECONDS = 6
MAX_ATTEMPTS = 3   # per image, so one bad image can't hold up everyone behind it
SHEETS = ("turnaround", "colorguide", "expressions")


def vary_workflow(wf: dict, image: str, denoise: float) -> dict:
    wf = dict(wf)
    wf["40"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    wf["41"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["40", 0], "vae": ["4", 2]}}
    wf["3"] = {**wf["3"], "inputs": {**wf["3"]["inputs"], "latent_image": ["41", 0], "denoise": denoise}}
    wf.pop("5")
    return wf


def _private(wf: dict) -> dict:
    wf["9"]["inputs"]["filename_prefix"] = "character_creator/c"   # ComfyUI's folder is wider open than a private link
    return wf


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


class Creator:
    # ponytail: one lock also covers ComfyUI calls in tick(), so a slow ComfyUI delays API replies by up to its
    # timeouts; give the worker its own lock if that's ever felt.
    def __init__(self, root: Path, comfy, rng=random, now=None, clock=time.monotonic):
        self.root, self.comfy, self.rng, self.clock = Path(root), comfy, rng, clock
        self._quiet_checks, self._quiet_since, self._gpu_owed = 0, 0.0, False
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        self._mutex = threading.RLock()
        self.queue_file = self.root / "queue.json"

    def _dir(self, cid: str) -> Path:
        if not isinstance(cid, str) or not TOKEN.fullmatch(cid):
            raise KeyError(cid)
        return self.root / "characters" / cid

    def _load(self, cid: str) -> dict:
        try:
            # Unreadable data raises instead of reading as empty, so it can't be overwritten.
            return json.loads((self._dir(cid) / "character.json").read_text())
        except FileNotFoundError:
            raise KeyError(cid) from None

    def _save(self, record: dict) -> dict:
        record["updated"] = self.now()
        write_json_atomic(self._dir(record["id"]) / "character.json", record)
        return self._view(record, self._jobs())

    def _jobs(self) -> list[dict]:
        return json.loads(self.queue_file.read_text()) if self.queue_file.exists() else []

    def _write_jobs(self, jobs: list[dict]) -> None:
        write_json_atomic(self.queue_file, jobs)

    def _file(self, cid: str, name: str) -> Path:
        return self._dir(cid) / ("candidates" if name.startswith("r") else "sheets") / name

    @staticmethod
    def _view(record: dict, jobs: list[dict]) -> dict:
        active = [j for j in jobs if j["status"] in ACTIVE]
        job = next((j for j in jobs if j["character"] == record["id"]), None)
        queue = None
        if job:
            queue = {"position": active.index(job) + 1 if job in active else None, "label": job["label"], "error": job["error"]}
        return {**record, "queue": queue}

    def create(self, kind, answers, by_owner: bool) -> dict:
        if kind not in KINDS:
            raise BadRequest(f"kind must be one of: {', '.join(KINDS)}")
        answers = clean_answers(answers)
        with self._mutex:
            now = self.now()
            cid = secrets.token_urlsafe(24)
            return self._save({
                "id": cid, "kind": kind, "status": "draft" if kind == "player" or by_owner else "suggested",
                "by_owner": by_owner, "answers": answers, "note": "", "seed": self.rng.randint(1, MAX_SEED),
                "rounds": [], "favourites": [], "picked": None,
                "sheets": {"turnaround": None, "colorguide": None, "expressions": []}, "created": now, "updated": now})

    def get(self, cid: str) -> dict:
        with self._mutex:
            return self._view(self._load(cid), self._jobs())

    def list_all(self) -> list[dict]:
        with self._mutex:
            jobs = self._jobs()
            folder = self.root / "characters"
            found = [self._view(self._load(p.name), jobs) for p in folder.iterdir() if TOKEN.fullmatch(p.name)] if folder.exists() else []
        return sorted(found, key=lambda r: (r["answers"]["name"].lower(), r["id"]))

    def update_answers(self, cid: str, answers) -> dict:
        with self._mutex:
            record = self._load(cid)
            if record["status"] in ("locked", "declined"):
                raise BadRequest(f"this character is {record['status']}, so its answers can't change")
            record["answers"] = clean_answers(answers)
            return self._save(record)

    @staticmethod
    def _can_render(record: dict) -> None:
        reasons = {"suggested": "this suggestion is waiting for review", "declined": "this suggestion was declined",
                   "locked": "this character is locked in"}
        if record["status"] in reasons:
            raise BadRequest(reasons[record["status"]])

    @staticmethod
    def _image(record: dict, round_no, n) -> str:
        images = next((r["images"] for r in record["rounds"] if r["n"] == round_no and type(round_no) is int), [])
        if type(n) is not int or not 1 <= n <= len(images):
            raise BadRequest("no such image")
        return images[n - 1]

    @staticmethod
    def _next_round(record: dict) -> int:
        return max((r["n"] for r in record["rounds"]), default=0) + 1

    def _enqueue(self, record: dict, label: str, round_no: int | None, items: list[dict], note: str = "", source=None) -> None:
        jobs = self._jobs()
        cid = record["id"]
        active = [j for j in jobs if j["status"] in ACTIVE]
        if any(j["character"] == cid for j in active):
            raise Busy("this character already has a batch in line; let it finish first")
        if len(active) >= MAX_WAITING:
            raise Busy(f"{MAX_WAITING} batches are already waiting; please try again in a few minutes")
        jobs = [j for j in jobs if j["character"] != cid]   # what's left of it is a failed batch this replaces
        self._write_jobs(jobs + [{"id": uuid.uuid4().hex, "character": cid, "label": label, "round": round_no, "status": "waiting",
                                  "items": items, "error": "", "note": note, "from": source}])

    def _candidates(self, record: dict, round_no: int, note: str, prepare=lambda wf: wf) -> list[dict]:
        pos, neg = candidate_prompt(to_design(record["answers"], record["kind"], record["seed"]))
        pos = rated(pos, record["answers"])
        if note:
            pos = f"{pos}, {note}"
        items = []
        for c in range(1, CANDIDATES_PER_ROUND + 1):
            seed = self.rng.randint(1, MAX_SEED)
            items.append({"name": f"r{round_no}-c{c}-{seed}.png", "workflow": prepare(_private(candidate_workflow(pos, neg, seed))),
                          "comfy_id": None, "done": False})
        return items

    def generate(self, cid: str, note: str = "") -> dict:
        with self._mutex:
            record = self._load(cid)
            note = clean_note(note, record["answers"])
            self._can_render(record)
            round_no = self._next_round(record)
            self._enqueue(record, "candidates", round_no, self._candidates(record, round_no, note), note)
            return self.get(cid)

    def vary(self, cid: str, round_no, n, strength, note: str = "") -> dict:
        if not isinstance(strength, str) or strength not in DENOISE:
            raise BadRequest("strength must be subtle or strong")
        with self._mutex:
            record = self._load(cid)
            note = clean_note(note, record["answers"])
            self._can_render(record)
            source = self._image(record, round_no, n)
            next_round = self._next_round(record)
            # The source is uploaded when the render starts, so a ComfyUI that's down only means waiting.
            items = self._candidates(record, next_round, note, lambda wf: vary_workflow(wf, "", DENOISE[strength]))
            for item in items:
                item["source"] = source
            self._enqueue(record, "variations", next_round, items, note, source)
            return self.get(cid)

    def retry(self, cid: str) -> dict:
        with self._mutex:
            self._load(cid)
            jobs = self._jobs()
            job = next((j for j in jobs if j["character"] == cid and j["status"] == "failed"), None)
            if job is None:
                raise BadRequest("there's no failed batch to retry")
            if sum(j["status"] in ACTIVE for j in jobs) >= MAX_WAITING:
                raise Busy(f"{MAX_WAITING} batches are already waiting; please try again in a few minutes")
            job.update(status="waiting", error="")
            for item in job["items"]:
                item["attempts"] = 0
            self._write_jobs(jobs)
            return self.get(cid)

    def pick(self, cid: str, round_no, n) -> dict:
        with self._mutex:
            record = self._load(cid)
            self._can_render(record)
            record["picked"] = self._image(record, round_no, n)
            record["seed"] = int(record["picked"].rsplit("-", 1)[1].removesuffix(".png"))   # sheets render from the picked look
            return self._save(record)

    def favourite(self, cid: str, round_no, n) -> dict:
        with self._mutex:
            record = self._load(cid)
            name = self._image(record, round_no, n)
            if name in record["favourites"]:
                record["favourites"].remove(name)
            else:
                record["favourites"].append(name)
            return self._save(record)

    def _sheet_items(self, record: dict, sheet: str, seed: int) -> list[dict]:
        design = to_design(record["answers"], record["kind"], seed, close_up=sheet == "expressions")
        if sheet == "expressions":
            items = []
            for i, (_label, pos, neg) in enumerate(expression_prompts(design), 1):
                wf = candidate_workflow(rated(pos, record["answers"]), neg, seed)
                wf["5"]["inputs"].update(width=EXPRESSION_SIZE[0], height=EXPRESSION_SIZE[1])
                items.append((f"expression-{i}.png", wf))
        else:
            pos, neg = sheet_prompt(design, sheet)
            items = [(f"{sheet}.png", sheet_workflow(rated(pos, record["answers"]), neg, seed))]
        return [{"name": name, "workflow": _private(wf), "comfy_id": None, "done": False} for name, wf in items]

    def lock(self, cid: str) -> dict:
        with self._mutex:
            record = self._load(cid)
            self._can_render(record)
            if not record["picked"]:
                raise BadRequest("pick a candidate before locking in")
            items = [item for sheet in SHEETS for item in self._sheet_items(record, sheet, record["seed"])]
            self._enqueue(record, "sheets", None, items)
            record["status"] = "locked"
            return self._save(record)

    def redo_sheet(self, cid: str, sheet) -> dict:
        if not isinstance(sheet, str) or sheet not in SHEETS:
            raise BadRequest(f"sheet must be one of: {', '.join(SHEETS)}")
        with self._mutex:
            record = self._load(cid)
            if record["status"] != "locked":
                raise BadRequest("lock the character in before redoing a sheet")
            # A new seed, or ComfyUI would hand back the same picture.
            self._enqueue(record, "sheets", None, self._sheet_items(record, sheet, self.rng.randint(1, MAX_SEED)))
            return self.get(cid)

    def accept(self, cid: str) -> dict:
        with self._mutex:
            record = self._suggestion(cid)
            record["status"] = "accepted"
            return self._save(record)

    def decline(self, cid: str, note) -> dict:
        if not isinstance(note, str):
            raise BadRequest("the note must be text")
        with self._mutex:
            record = self._suggestion(cid)
            record.update(status="declined", note=note.strip()[:MAX_DECLINE_NOTE])
            return self._save(record)

    def _suggestion(self, cid: str) -> dict:
        record = self._load(cid)
        if record["status"] != "suggested":
            raise BadRequest("that isn't a suggestion waiting for review")
        return record

    def delete(self, cid: str) -> None:
        with self._mutex:
            self._load(cid)
            self._write_jobs([j for j in self._jobs() if j["character"] != cid])
            shutil.rmtree(self._dir(cid))

    def image_path(self, cid: str, name: str) -> Path:
        if not NAME.fullmatch(name):
            raise KeyError(name)
        path = self._file(cid, name)
        if not path.is_file():
            raise KeyError(name)
        return path

    def _finish_batch(self, jobs: list[dict], job: dict) -> None:
        """All its images are saved: put them on the record, or fail the batch if the record can't take them."""
        names = [i["name"] for i in job["items"]]
        try:
            record = self._load(job["character"])
            if job["label"] == "sheets":
                expressions = [n for n in names if n.startswith("expression-")]
                if expressions:
                    record["sheets"]["expressions"] = expressions
                record["sheets"].update((n.removesuffix(".png"), n) for n in names if n not in expressions)
            elif not any(r["n"] == job["round"] for r in record["rounds"]):   # a crash before the queue was saved repeats this step
                record["rounds"].append({"n": job["round"], "type": "vary" if job["label"] == "variations" else "reroll",
                                         "from": job["from"], "note": job["note"], "images": names})
            self._save(record)
        except KeyError as e:
            if e.args and e.args[0] == job["character"]:   # the character's gone, and its images with it
                jobs.remove(job)
            else:
                self._fail(job, "This character's record is damaged")
        except (ValueError, TypeError, AttributeError):
            self._fail(job, "This character's record is damaged")
        else:
            jobs.remove(job)

    @staticmethod
    def _fail(job: dict, error: str) -> None:
        job.update(status="failed", error=error)
        for item in job["items"]:
            item["comfy_id"] = None

    def _tried(self, jobs: list[dict], job: dict, item: dict, error: OSError) -> None:
        """A try went wrong. A 4xx won't change, and the last attempt fails the batch; anything else raises so the worker logs it."""
        if isinstance(error, urllib.error.HTTPError) and error.code < 500:
            self._fail(job, f"ComfyUI refused this image ({error.code})")
        elif item["attempts"] >= MAX_ATTEMPTS:
            self._fail(job, f"This image failed after {MAX_ATTEMPTS} tries")
        else:
            self._write_jobs(jobs)
            raise error

    def _poll(self, jobs: list[dict], job: dict, item: dict) -> bool:
        """Follow the render in progress. True if it's still going."""
        queue = self.comfy.queue()   # read before history: a job that's left the queue is then already in history
        in_comfy = {q[1] for q in queue["queue_running"] + queue["queue_pending"]}
        entry = self.comfy.history(item["comfy_id"])
        if entry and entry.get("status", {}).get("completed"):
            images = entry.get("outputs", {}).get("9", {}).get("images", [])
            if images:
                try:
                    data = self.comfy.image(images[0])
                except OSError as e:
                    item["attempts"] += 1
                    self._tried(jobs, job, item, e)
                else:
                    _write_bytes_atomic(self._file(job["character"], item["name"]), data)
                    item["done"] = True
                    if all(i["done"] for i in job["items"]):
                        self._finish_batch(jobs, job)
                    else:
                        job["status"] = "waiting"
            else:
                self._fail(job, "ComfyUI finished without an image")
        elif entry and entry.get("status", {}).get("status_str") == "error":
            self._fail(job, "ComfyUI hit an error on this image")
        elif item["comfy_id"] in in_comfy:
            return True
        elif item["attempts"] >= MAX_ATTEMPTS:
            self._fail(job, f"ComfyUI lost this image {MAX_ATTEMPTS} times")
        else:   # a restart on either side: put it back in line rather than failing it
            item["comfy_id"] = None
            job["status"] = "waiting"
        self._write_jobs(jobs)
        return False

    def _submit(self, jobs: list[dict], job: dict) -> None:
        item = next((i for i in job["items"] if not i["done"]), None)
        if item is None:   # a retry of a batch whose images are all saved
            self._finish_batch(jobs, job)
            return self._write_jobs(jobs)
        if not job.get("ollama_freed"):
            job["ollama_freed"] = True
            try:
                self.comfy.free_ollama()
            except OSError:
                pass   # best effort: a model left loaded slows the render, it doesn't stop it
        item["attempts"] = item.get("attempts", 0) + 1
        try:
            if item.get("source"):
                data = self._file(job["character"], item["source"]).read_bytes()
                # A random name: ComfyUI's input folder is shared, and it must not reveal the character's link.
                item["workflow"]["40"]["inputs"]["image"] = self.comfy.upload(f"{uuid.uuid4().hex}.png", data)
            item["comfy_id"] = self.comfy.submit(item["workflow"])
            job["status"] = "rendering"
        except FileNotFoundError:
            self._fail(job, "The image to vary is gone")
        except OSError as e:
            self._tried(jobs, job, item, e)
        self._write_jobs(jobs)

    def _quiet(self) -> bool:
        """Has ComfyUI's queue stayed empty long enough? Every call is one check; anything in the queue starts it over."""
        queue = self.comfy.queue()
        if queue["queue_running"] or queue["queue_pending"]:
            self._quiet_checks = 0
            return False
        if not self._quiet_checks:
            self._quiet_since = self.clock()
        self._quiet_checks += 1
        return self._quiet_checks >= QUIET_CHECKS and self.clock() - self._quiet_since >= QUIET_SECONDS

    def tick(self) -> None:
        """One step of the worker. ComfyUI being down raises, and leaves everything in line for the next tick."""
        with self._mutex:
            jobs = self._jobs()
            if not any(j["status"] in ACTIVE for j in jobs) and not self._gpu_owed:
                self._quiet_checks = 0
                return
            rendering = next(((j, i) for j in jobs if j["status"] == "rendering" for i in j["items"] if i["comfy_id"] and not i["done"]), None)
            if rendering:
                self._gpu_owed = True
                if self._poll(jobs, *rendering):
                    return
            job = next((j for j in jobs if j["status"] in ACTIVE), None)
            if job:
                self._gpu_owed = True
            if not self._quiet():
                return
            self._quiet_checks = 0
            if job:
                self._submit(jobs, job)
            else:
                self._gpu_owed = False
                try:
                    self.comfy.free_comfy()   # hand the GPU back so the narrator's model can load
                except OSError:
                    pass


def run_worker(creator: Creator, stop: threading.Event, interval: float = 2) -> None:
    while not stop.wait(interval):
        try:
            creator.tick()
        except Exception as e:   # the worker outlives anything: the next tick tries again
            print(f"character creator worker: {e}", file=sys.stderr, flush=True)


def export(root: Path, cid: str, designs_dir: Path, design_dir: Path) -> Path:
    """An NPC or AI character becomes a normal approved design in the repo, with its picked image where the studio looks."""
    creator = Creator(root, comfy=None)
    record = creator.get(cid)
    if record["kind"] == "player":
        raise BadRequest("player characters aren't stored in the repo, so they can't be exported")
    if not record["picked"]:
        raise BadRequest("pick a candidate before exporting")
    design = to_design(record["answers"], record["kind"], record["seed"])
    design.status = "approved"
    a = record["answers"]
    place = ", ".join(x for x in (a.get("world_role"), f"home: {a['home']}" if a.get("home") else None) if x)
    if place:   # "draft:" is what Image Studio shows as the character's role
        design.notes.append(f"{dt.date.today().isoformat()} draft: {place}")
    design.notes.append(f"{dt.date.today().isoformat()} from the character creator ({record['kind']})")
    if a.get("signature"):
        design.notes.append(f"signature item, in the tags and not in held: {a['signature']}. Move it to held by hand if it floats on close-ups.")
    validate(design)
    slug = design.slug
    if not slug:
        raise BadRequest("this name has no letters a file name can use: edit the name first")
    path = Path(designs_dir) / f"{slug}.toml"
    folder = Path(design_dir) / slug
    if path.exists() or folder.exists():
        raise BadRequest(f"{slug} already exists: rename this character first")
    image = folder / "candidates" / f"r1-c1-{design.seed}.png"
    image.parent.mkdir(parents=True)
    shutil.copyfile(creator.image_path(cid, record["picked"]), image)
    save_design(design, path)
    return path


def owner_token(root: Path) -> str:
    """Created once, readable only by the service. It's never logged or shown: the owner reads the file."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "owner.token"
    # Written in full first and then linked into place, so a crash can't leave an empty file for a later start to trust.
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")   # mode 0o600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(24) + "\n")
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
    finally:
        os.unlink(tmp)
    token = path.read_text().strip()
    if not token:
        raise ValueError(f"{path} is empty: delete it to have a new owner link made")
    return token


PUBLIC_ACTIONS = {
    "generate": lambda c, cid, b: c.generate(cid, b.get("note", "")),
    "vary": lambda c, cid, b: c.vary(cid, b.get("round"), b.get("n"), b.get("strength"), b.get("note", "")),
    "pick": lambda c, cid, b: c.pick(cid, b.get("round"), b.get("n")),
    "favourite": lambda c, cid, b: c.favourite(cid, b.get("round"), b.get("n")),
    "lock": lambda c, cid, b: c.lock(cid),
    "sheet": lambda c, cid, b: c.redo_sheet(cid, b.get("sheet")),
    "retry": lambda c, cid, b: c.retry(cid),
}
OWNER_ACTIONS = {
    **PUBLIC_ACTIONS,
    "accept": lambda c, cid, b: c.accept(cid),
    "decline": lambda c, cid, b: c.decline(cid, b.get("note", "")),
}


def options() -> dict:
    return {"questions": QUESTIONS, "strengths": list(DENOISE), "sheets": list(SHEETS), "expressions": [e[0] for e in EXPRESSIONS],
            "candidates": CANDIDATES_PER_ROUND}


def make_server(host: str, port: int, creator: Creator, owner: str) -> ThreadingHTTPServer:
    if not owner:
        raise ValueError("the owner token is empty")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload) -> None:
            self._bytes(status, json.dumps(payload).encode(), "application/json", "no-store")

        def _bytes(self, status: int, raw: bytes, ctype: str, cache: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _not_found(self) -> None:
            self._send(404, {"error": "not found"})

        def _guarded(self, fn) -> None:
            try:
                fn()
            except KeyError:
                self._not_found()
            except Busy as e:
                self._send(429, {"error": str(e)})
            except BadRequest as e:
                self._send(400, {"error": str(e)})
            except OSError:   # the disk: requests don't touch ComfyUI, and paths in the message hold tokens
                self._send(502, {"error": "the character store didn't answer"})
            except ValueError:
                self._send(500, {"error": "the character's data is unreadable"})

        def _route(self) -> tuple[bool, list[str]] | None:
            """(is the owner, path parts), or None for a path that doesn't exist, which a wrong owner token also is."""
            path = self.path.split("?", 1)[0]
            if not path.startswith(PREFIX + "/"):
                return None
            parts = path[len(PREFIX) + 1:].split("/")
            if parts[0] != "owner":
                return False, parts
            if len(parts) < 3 or not parts[1] or not owner or not hmac.compare_digest(parts[1].encode(), owner.encode()):
                return None
            return True, parts[2:]

        def do_GET(self):
            match self._route():
                case (_, ["options"]):
                    self._send(200, options())
                case (True, ["characters"]):
                    self._guarded(lambda: self._send(200, {"characters": creator.list_all()}))
                case (_, ["characters", cid]):
                    self._guarded(lambda: self._send(200, creator.get(cid)))
                case (_, ["characters", cid, "image", name]):
                    self._guarded(lambda: self._bytes(200, creator.image_path(cid, name).read_bytes(), "image/png", "private"))
                case _:
                    self._not_found()

        def _write(self, method: str) -> None:
            route = self._route()
            if route is None:
                return self._not_found()
            is_owner, parts = route
            actions = OWNER_ACTIONS if is_owner else PUBLIC_ACTIONS
            cid, status = None, 200
            match (method, parts):
                case ("POST", ["characters"]):
                    status = 201

                    def run(b):
                        return creator.create(b.get("kind"), b.get("answers"), by_owner=is_owner)
                case ("POST", ["characters", cid, action]) if action in actions:
                    def run(b):
                        return actions[action](creator, cid, b)
                case ("PUT", ["characters", cid, "answers"]):
                    def run(b):
                        return creator.update_answers(cid, b)
                case ("DELETE", ["characters", cid]):
                    def run(b):
                        creator.delete(cid)
                        return {}
                case _:
                    return self._not_found()
            self.close_connection = True   # any refused body stays unread
            # Requiring JSON and a matching Origin stops other websites writing through a player's browser.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": "expected JSON"})
            origin = self.headers.get("Origin")
            if origin is not None and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                return self._send(403, {"error": "wrong origin"})
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return self._send(400, {"error": "bad length"})
            if not 0 <= length <= MAX_BODY:
                return self._send(413, {"error": "too large"})
            try:
                raw = self.rfile.read(length)
                body = json.loads(raw) if raw else {}
            except ValueError:
                return self._send(400, {"error": "bad JSON"})
            if not isinstance(body, dict):
                return self._send(400, {"error": "expected an object"})

            def respond():
                # A character link reads its own record, but NPCs and AI characters only change on the owner route,
                # so whoever suggested one can't re-roll it after it's accepted.
                if cid is not None and not is_owner and creator.get(cid)["kind"] != "player":
                    return self._send(403, {"error": "only the owner can change this character"})
                self._send(status, run(body))

            self._guarded(respond)

        def do_POST(self):
            self._write("POST")

        def do_PUT(self):
            self._write("PUT")

        def do_DELETE(self):
            self._write("DELETE")

        def log_message(self, *args):
            pass   # paths hold the private links

    return ThreadingHTTPServer((host, port), Handler)


def export_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="tools.character_creator export")
    parser.add_argument("id")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--designs-dir", type=Path, required=True)
    parser.add_argument("--design-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(export(args.state, args.id, args.designs_dir, args.design_dir))
    except BadRequest as e:
        raise SystemExit(str(e)) from None
    except KeyError:
        raise SystemExit("no character with that id") from None


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["export"]:
        return export_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--comfy", default="http://127.0.0.1:8188")
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args(argv)
    creator = Creator(args.root, Comfy(args.comfy, args.ollama))
    server = make_server(args.host, args.port, creator, owner_token(args.root))
    threading.Thread(target=run_worker, args=(creator, threading.Event()), daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
