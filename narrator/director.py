"""The director: a tension number the engine keeps itself, breathers after a peak, and an owner-approved event when
play goes quiet. Each event leaves a lead on the objectives so it drives the story. No model calls.
See docs/superpowers/specs/2026-11-22-director-design.md (Left 4 Dead's AI Director; storylets)."""

import json
import tomllib
from functools import cache
from pathlib import Path

from engine.session import Session
from narrator import promises
from narrator.cast import _player_turns
from narrator.world import _where, kuroshio

TENSION_MAX, PEAK, RELEASE = 10, 8, 5
BREATHER_TURNS, QUIET_AT, QUIET_TURNS = 2, 1, 4
NO_REPEAT, MIN_GAP = 40, 6
PACING = "Pacing: let this moment breathe - no new threats or arrivals this turn."
_EVENTS = Path(__file__).resolve().parent / "worlds" / "events.toml"
_NEEDS = {"owes", "promise_open", "throttled"}


@cache
def events() -> tuple[dict, ...]:
    raw = tomllib.loads(_EVENTS.read_text(encoding="utf-8"))["event"]
    for e in raw:
        if set(e.get("needs", [])) - _NEEDS:
            raise ValueError(f"event {e['id']!r}: unknown needs {e['needs']}")
        if not e.get("lead") and not e.get("needs"):
            raise ValueError(f"event {e['id']!r}: needs a lead (only state-tied events may go without)")
    return tuple(raw)


def pacing_line(session: Session) -> str:
    return PACING if session.breather > 0 else ""


def _rolls_this_turn(session: Session) -> list[str]:
    """Outcomes of the rolls since the player's last action line (a roll-resolution turn holds its roll)."""
    actors = tuple(f"{pid}: " for pid in session.characters)
    starts = [i for i, line in enumerate(session.log) if line.startswith(actors)]
    outcomes = []
    for line in session.log[starts[-1] if starts else 0:]:
        if line.startswith("[roll: "):
            try:
                outcomes.append(json.loads(line[len("[roll: "):-1]).get("outcome", ""))
            except json.JSONDecodeError:
                outcomes.append("")
    return outcomes


def _met(session: Session, player_id: str, need: str) -> bool:
    c = session.characters[player_id]
    return {"owes": c.installments_owed > 0, "promise_open": bool(session.promises),
            "throttled": bool(c.throttled)}[need]


def pick(session: Session, player_id: str) -> dict | None:
    """Conditions met, not used in the last 40 turns; this district before anywhere, tied to the player before
    generic, then the one used longest ago (never used first)."""
    now = _player_turns(session)
    district = _where(kuroshio(), session.location)[1]
    here = district.name if district else None
    ok = [e for e in events()
          if (not e.get("where") or here in e["where"])
          and all(_met(session, player_id, n) for n in e.get("needs", []))
          and now - session.events_used.get(e["id"], -NO_REPEAT) >= NO_REPEAT]
    if not ok:
        return None
    return min(ok, key=lambda e: (not e.get("where"), not e.get("needs"), session.events_used.get(e["id"], -1)))


def fire(session: Session, event: dict) -> None:
    text = event["text"]
    if session.promises:
        oldest = session.promises[0]
        text = text.replace("{who}", oldest["who"]).replace("{what}", oldest["what"])
    session.pending_world_events.append(text)
    session.events_used[event["id"]] = _player_turns(session)
    session.log.append(f"[director: {event['id']}]")
    if event.get("lead"):
        promises.add_lead(session, event["lead"])


def tick(session: Session, player_id: str, health_before: int) -> None:
    """End of a player's turn, after the referee. Not on the set-up turn that opened a roll."""
    if player_id in session.pending_rolls:
        return
    outcomes = _rolls_this_turn(session)
    hurt = session.characters[player_id].health < health_before
    if session.in_combat:
        rise = 3
    elif outcomes or hurt:
        rise = 2 * bool(outcomes) + 2 * (hurt or "failure" in outcomes)
    else:
        rise = -1
    session.tension = max(0, min(TENSION_MAX, session.tension + rise))
    if session.breather > 0:
        session.breather -= 1  # this turn carried the pacing line
    elif session.tension >= PEAK and not session.in_combat:
        session.breather, session.tension = BREATHER_TURNS, RELEASE  # the peak is spent; let it breathe
        session.log.append("[director: breather]")
    session.quiet_turns = session.quiet_turns + 1 if session.tension <= QUIET_AT else 0
    last = max(session.events_used.values(), default=-MIN_GAP)
    if (session.quiet_turns >= QUIET_TURNS and not session.breather and not session.pending_world_events
            and _player_turns(session) - last >= MIN_GAP and (event := pick(session, player_id))):
        fire(session, event)
        session.quiet_turns = 0
