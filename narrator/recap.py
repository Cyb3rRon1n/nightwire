"""The night recap (spec 2026-11-24-night-recap-design.md): a played session cut into turns, scored by what the
engine logged for each, and kept as 3 to 12 storyboard panels plus a facts box. Deterministic; no model calls.
Picking follows Wildermyth (quotas per kind of beat) and story sifting (a short written list of beats)."""

import json
import re

from engine.session import Session
from narrator.place_art import district_art, location_art
from narrator.world import _where, kuroshio

MAX_PANELS, MIN_PANELS, RUN_MAX = 12, 3, 3  # RUN_MAX: the least a scene may hold
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_SPEECH = re.compile(r"^([^:\[\]]{1,40}):\s+(.+)$")
_SCORES = (("[promise: ", 3), ("[promise kept: ", 3), ("[promise broken: ", 3),
           ("[pressure: ", 2), ("[person: ", 2), ("[mark: ", 1))


def _district(place: str | None) -> str | None:
    d = _where(kuroshio(), place)[1]
    return d.name if d else None


def turns(session: Session) -> list[dict]:
    """The log cut at each player action line; a roll's set-up and its resolution stay one turn."""
    actors = {f"{pid}: ": pid for pid in session.characters}
    trail = {n: loc for n, loc in session.trail}
    out: list[dict] = []
    for line in session.log:
        pid = next((p for prefix, p in actors.items() if line.startswith(prefix)), None)
        if pid is not None:
            n = len(out) + 1
            place = trail.get(n) or next((trail[k] for k in sorted(trail, reverse=True) if k < n and trail[k]), None)
            out.append({"n": n, "player": session.characters[pid].name, "action": line[len(pid) + 2:].strip(),
                        "place": place or session.location or "", "lines": [], "notes": [], "image": None})
        elif out:
            t = out[-1]
            if line.startswith("[image: ") and line.endswith("]"):
                t["image"] = t["image"] or line[len("[image: "):-1]
            (t["notes"] if line.startswith("[") else t["lines"]).append(line)
    return out


def score(t: dict) -> int:
    total = 0
    rated = [n for n in t["notes"] if n.startswith("[rated: ")]
    if rated and rated[-1] == "[rated: like]":  # a re-rated turn counts its last rating once
        total += 3
    for note in t["notes"]:
        if note.startswith("[roll: "):
            try:
                outcome = json.loads(note[len("[roll: "):-1]).get("outcome")
            except json.JSONDecodeError:
                outcome = None
            total += {"clean_success": 2, "failure": 2, "complication": 1}.get(outcome, 0)
        elif note.startswith("[director: ") and note != "[director: breather]":
            total += 2
        else:
            total += next((v for prefix, v in _SCORES if note.startswith(prefix)), 0)
    return total


def _pick(ts: list[dict]) -> list[dict]:
    if len(ts) <= MIN_PANELS:
        return ts
    keep = {ts[0]["n"], ts[-1]["n"]}
    seen: set[str | None] = set()
    for t in ts:  # an establishing panel for each new district (a scene-to-scene cut)
        d = _district(t["place"])
        if d not in seen:
            seen.add(d)
            keep.add(t["n"])
    by_n = {t["n"]: t for t in ts}
    # A scene is a stretch of turns in one place; each gets panels in proportion to its turns, at least RUN_MAX,
    # so a busy scene can't crowd out the rest and a night spent in one place still fills the sheet.
    scene, scenes = {}, 0
    for i, t in enumerate(ts):
        scenes += i == 0 or t["place"] != ts[i - 1]["place"]
        scene[t["n"]] = scenes
    size = {k: sum(v == k for v in scene.values()) for k in set(scene.values())}
    cap = {k: max(RUN_MAX, -(-MAX_PANELS * n // len(ts))) for k, n in size.items()}

    def run_ok(chosen: set[int]) -> bool:
        return all(sum(scene[n] == k for n in chosen) <= cap[k] for k in cap)

    for t in sorted(ts, key=lambda t: (-score(t), t["n"])):
        if len(keep) >= MAX_PANELS:
            break
        if score(t) and t["n"] not in keep and run_ok(keep | {t["n"]}):
            keep.add(t["n"])
    for t in ts:  # a quiet night still gets its minimum (review 2026-11-24): the earliest turns that fit
        if len(keep) >= min(MIN_PANELS, len(ts)):
            break
        if t["n"] not in keep and run_ok(keep | {t["n"]}):
            keep.add(t["n"])
    if len(keep) > MAX_PANELS:  # more districts than room: keep the first and last, then the earliest
        middle = sorted(keep - {ts[0]["n"], ts[-1]["n"]})[:MAX_PANELS - 2]
        keep = {ts[0]["n"], ts[-1]["n"], *middle}
    return [by_n[n] for n in sorted(keep)]


def _portrait(name: str) -> str | None:
    from server.views import _portrait as portrait  # late: views imports the narrator package
    return portrait(name)


def _line(t: dict, players: set[str]) -> tuple[str | None, str]:
    speech = []
    for line in t["lines"]:
        m = _SPEECH.match(line)
        who = m.group(1).strip() if m else ""
        words = who.split()
        named = all(w[:1].isupper() for w in words) and 0 < len(words) <= 3 and words[0].lower() not in ("a", "an", "the")
        if named and who.lower() not in players and 4 <= len(m.group(2).split()) <= 20:  # not "A voice calls out"
            speech.append((who, m.group(2).strip().strip("'\"“”‘’ ")))
    if speech:
        return min(speech, key=lambda s: len(s[1]))
    prose = next((l for l in t["lines"] if not _SPEECH.match(l)), "")
    first = _SENTENCE.split(prose.strip(), maxsplit=1)[0] if prose else ""
    return None, first if len(first) <= 160 else first[:159].rstrip() + "…"


def panels(session: Session) -> list[dict]:
    players = {c.name.strip().lower() for c in session.characters.values()} | {p.lower() for p in session.characters}
    out = []
    for t in _pick(turns(session)):
        speaker, text = _line(t, players)
        art = t["image"] or location_art(t["place"])
        if not art and (d := district_art(t["place"])):
            art = f"place-art/{d.name}"
        out.append({"n": t["n"], "place": t["place"], "caption": t["place"] or "Kuroshio", "art": art,
                    "speaker": speaker, "portrait": _portrait(speaker) if speaker else None, "text": text,
                    "action": f"{t['player']}: {t['action']}"})
    return out


def facts(session: Session) -> dict:
    done = [j for j in session.journal if j.get("kind") in ("kept", "broken", "called in")]
    return {"people": [f"{n}, {p['who']}" for n, p in session.people.items()],
            "promises_open": [f"{p['who']}: {p['what']}" for p in session.promises],
            "promises_done": [f"{j['text']} ({j['kind']})" for j in done],
            "leads": list(session.active_objectives), "night": session.night}
