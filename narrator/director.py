"""The director: a tension number the engine keeps itself, breathers after a peak, and an owner-approved event when
play goes quiet. Each event leaves a lead on the objectives so it drives the story. No model calls.
See docs/superpowers/specs/2026-11-22-director-design.md (Left 4 Dead's AI Director; storylets)."""

import json
import tomllib
from functools import cache
from pathlib import Path

from engine.session import Session
from narrator import gossip, people, places, promises
from narrator.cast import _player_turns
from narrator.world import _where, kuroshio

TENSION_MAX, PEAK, RELEASE = 10, 8, 5
BREATHER_TURNS, QUIET_TURNS = 2, 4
NO_REPEAT, MIN_GAP = 40, 6
PACING = "Pacing: let this moment breathe - no new threats or arrivals this turn."
_EVENTS = Path(__file__).resolve().parent / "worlds" / "events.toml"
_NEEDS = {"owes", "promise_open", "throttled", "people", "lockdown"}


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
    return PACING if session.breather > 0 and not session.in_combat else ""


def _rolls_this_turn(session: Session) -> list[dict]:
    """The rolls since the player's last action line (a roll-resolution turn holds its roll)."""
    actors = tuple(f"{pid}: " for pid in session.characters)
    starts = [i for i, line in enumerate(session.log) if line.startswith(actors)]
    outcomes = []
    for line in session.log[starts[-1] if starts else 0:]:
        if line.startswith("[roll: "):
            try:
                outcomes.append(json.loads(line[len("[roll: "):-1]))
            except json.JSONDecodeError:
                outcomes.append({})
    return outcomes


def _met(session: Session, player_id: str, need: str) -> bool:
    c = session.characters[player_id]
    return {"owes": c.installments_owed > 0, "promise_open": bool(session.promises),
            "throttled": bool(c.throttled), "people": people.comeback(session) is not None,
            "lockdown": False}[need]  # lockdown fires from places.heat, never by a quiet spell


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
    # Someone the player met coming back counts as local: it is about them (emerging characters spec).
    return min(ok, key=lambda e: (not (e.get("where") or "people" in e.get("needs", [])), not e.get("needs"),
                                  session.events_used.get(e["id"], -1)))


def fire(session: Session, event: dict) -> None:
    text, lead = event["text"], event.get("lead", "")
    if "people" in event.get("needs", []) and (name := people.comeback(session)):
        p = session.people[name]
        p["returned"] = _player_turns(session)
        fill = {"{name}": name, "{who}": p["who"], "{what}": p["what"]}
        for k, v in fill.items():
            text, lead = text.replace(k, v), lead.replace(k, v)
        if name not in session.present:
            session.present.append(name)
    elif session.promises:
        oldest = session.promises[0]
        text = text.replace("{who}", oldest["who"]).replace("{what}", oldest["what"])
    session.pending_world_events.append(text)
    session.events_used[event["id"]] = _player_turns(session)
    session.log.append(f"[director: {event['id']}]")
    if lead:
        promises.add_lead(session, lead)


def tick(session: Session, player_id: str, health_before: int) -> None:
    """End of a player's turn, after the referee. Not on the set-up turn that opened a roll."""
    if player_id not in session.characters or player_id in session.pending_rolls:
        return
    rolls = _rolls_this_turn(session)
    outcomes = [r.get("outcome", "") for r in rolls]
    hurt = session.characters[player_id].health < health_before
    places.arrive(session)
    if any(r.get("skill") in places._FIGHT_SKILLS for r in rolls):  # a roll to fight is the player's own doing
        gossip.record(session, f"{session.characters[player_id].name} got into a fight at "
                               f"{places.key(session) or 'the block'}", False)
    # Blades in the Dark: at 9 heat the district locks down; once per 40 turns, so a long fight sweeps once.
    lockdown = next(e for e in events() if e["id"] == "lockdown")
    if (places.heat(session, rolls, hurt)
            and _player_turns(session) - session.events_used.get("lockdown", -NO_REPEAT) >= NO_REPEAT):
        fire(session, {**lockdown, "text": lockdown["text"].replace("{place}", places.key(session) or "the block")})
        places.cool_after_lockdown(session)
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
    # Calm turns in a row, counted through a breather (soak 2026-11-22: waiting for tension to fall to 1 first
    # meant 8 calm turns, so the walk home and sleep never got an event).
    session.quiet_turns = session.quiet_turns + 1 if rise < 0 else 0
    gossip.tick(session)
    last = max(session.events_used.values(), default=-MIN_GAP)
    if (session.quiet_turns >= QUIET_TURNS and not session.breather and not session.pending_world_events
            and _player_turns(session) - last >= MIN_GAP and (event := pick(session, player_id))):
        fire(session, event)
        session.quiet_turns = 0
