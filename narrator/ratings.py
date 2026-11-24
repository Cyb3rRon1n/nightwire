"""Liked turns: 👍/👎 on the newest turn teach the narrator now (one liked example, a short avoid list) and are saved
with their full prompt as training data for later (KTO). Players are asked only in calm check-ins; per-turn buttons
are developer mode. See docs/superpowers/specs/2026-11-22-liked-turns-design.md."""

import json
import os
import time
from collections import Counter
from pathlib import Path

from engine.session import Session
from narrator.cast import _player_turns

REASONS = {"repeats": "repeating yourself", "acted_for_me": "deciding what they do", "dull": "dull, nothing happening",
           "wrong_facts": "getting facts wrong", "too_long": "going on too long"}
EXAMPLE_MAX = 600
_RECENT_LINES = 20
_AVOID_WINDOW, _AVOID_MIN = 30, 2
CHECKIN_FIRST, CHECKIN_EVERY, _CALM_TURNS = 10, 20, 3
EXAMPLE_HEADER = "A turn this player liked (match its feel and pacing; never reuse its words):"


def ratings_path() -> Path:
    return Path(os.environ.get("NIGHTWIRE_RATINGS", Path(__file__).resolve().parent.parent / "design-data"
                               / "turn-ratings.jsonl"))


def _read() -> list[dict]:
    path = ratings_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:  # a torn last line must not lose every rating before it
            continue
    return rows


def note_turn(session: Session, prompt: str, action: str, narration: str) -> None:
    """Called after each narrated turn: what a rating of the newest turn will be saved with."""
    session.last_turn = {"id": len(session.log), "prompt": prompt, "action": action, "narration": narration,
                         "location": session.location, "present": list(session.present)}
    session.last_rating = None
    session.checkin_open = False  # a check-in lasts one turn; maybe_checkin reopens it only if still calm


def clear_turn(session: Session) -> None:
    session.last_turn = session.last_rating = None
    session.checkin_open = False


def rate(session: Session, like: bool, reason: str | None) -> None:
    turn = session.last_turn
    if not turn:
        raise ValueError("no turn to rate")
    if reason is not None and reason not in REASONS:
        raise ValueError(f"unknown reason: {reason!r}")
    checkin = session.checkin_open
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": session.session_id, "turn": turn["id"], "like": like,
           "reason": None if like else reason, "checkin": checkin,
           **{k: turn[k] for k in ("prompt", "action", "narration", "location", "present")}}
    # ponytail: rewrites the whole file on every rating; an append-only log + compaction if it ever gets large.
    rows = [r for r in _read() if (r.get("session"), r.get("turn")) != (session.session_id, turn["id"])]
    path = ratings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [*rows, row]), encoding="utf-8")
    tmp.replace(path)
    session.log.append(f"[rated: {'like' if like else 'dislike'}]")  # the night recap scores liked turns
    session.last_rating = {"like": like, "reason": row["reason"]}
    session.checkin_open = False


def dismiss_checkin(session: Session) -> None:
    session.checkin_open = False


def maybe_checkin(session: Session) -> None:
    """A check-in only in a calm stretch: no combat, no roll waiting, no roll in the player's last 3 turns."""
    now = _player_turns(session)
    if session.checkin_open or not session.last_turn or now < CHECKIN_FIRST:
        return
    if session.checkin_turn is not None and now - session.checkin_turn < CHECKIN_EVERY:
        return
    if session.in_combat or session.pending_rolls:
        return
    actors = tuple(f"{pid}: " for pid in session.characters)
    starts = [i for i, line in enumerate(session.log) if line.startswith(actors)]
    since = starts[-_CALM_TURNS] if len(starts) >= _CALM_TURNS else 0
    if any(line.startswith("[roll") for line in session.log[since:]):
        return
    session.checkin_open, session.checkin_turn = True, now


def example(session: Session) -> dict | None:
    """One liked turn: same place with someone the same present, then same place, then the newest. Never one still in
    the recent log (it would only repeat what just happened)."""
    recent = "\n".join(session.log[-_RECENT_LINES:])
    # Narration is saved as its segments joined by newlines, each its own log line: compare the first one.
    liked = [r for r in _read() if r.get("like") and r.get("narration")
             and r["narration"].split("\n")[0][:80] not in recent]
    if not liked:
        return None
    here = [r for r in liked if r.get("location") and r["location"] == session.location]
    people = [r for r in here if set(r.get("present") or []) & set(session.present)]
    return (people or here or liked)[-1]


def example_block(session: Session) -> tuple[str, list[str]]:
    """The prompt block and the narration sentences the repeat cut should treat as already said."""
    r = example(session)
    if r is None:
        return "", []
    narration = r["narration"][:EXAMPLE_MAX].rsplit(" ", 1)[0] if len(r["narration"]) > EXAMPLE_MAX else r["narration"]
    return f"{EXAMPLE_HEADER}\n{r['action']} → {narration}", [narration]


def avoid_line() -> str:
    reasons = Counter(r["reason"] for r in _read()[-_AVOID_WINDOW:] if not r.get("like") and r.get("reason") in REASONS)
    top = [REASONS[k] for k, n in reasons.most_common(2) if n >= _AVOID_MIN]
    return f"The player has disliked: {'; '.join(top)}." if top else ""
