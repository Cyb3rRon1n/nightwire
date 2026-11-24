"""Pressure clocks: written threats that fill from what happens in their district and each new night, ease when the
player finishes their leads, and send portents to the narrator (Blades in the Dark clocks, Dungeon World fronts,
Citizen Sleeper cycles). The engine owns them; no model calls.
See docs/superpowers/specs/2026-11-24-pressure-clocks-design.md. Not narrator/clock.py, the night clock."""

import tomllib
from functools import cache
from pathlib import Path

from engine.session import Session
from narrator import promises
from narrator.cast import _player_turns
from narrator.places import _FIGHT_SKILLS
from narrator.world import _where, kuroshio

SIZES, TRIGGERS, REST, SHOWN_MAX = (4, 6, 8), {"fight", "miss", "heat", "night", "lead_done"}, 40, 2
_CLOCKS = Path(__file__).resolve().parent / "worlds" / "clocks.toml"


def validate(raw: list[dict]) -> None:
    districts = {d.name for d in kuroshio().districts}
    for c in raw:
        cid = c.get("id", "?")
        if c.get("size") not in SIZES:
            raise ValueError(f"clock {cid!r}: size must be one of {SIZES}")
        if bad := (set(c.get("ticks", [])) | set(c.get("eases", []))) - TRIGGERS:
            raise ValueError(f"clock {cid!r}: unknown triggers {sorted(bad)}")
        if not c.get("where") or set(c["where"]) - districts:
            raise ValueError(f"clock {cid!r}: where must name districts, got {c.get('where')}")
        if any(not 0 < int(s) < c["size"] for s in c.get("portents", {})):
            raise ValueError(f"clock {cid!r}: portent stages must be between 0 and {c['size']}")
        if not c.get("full") or not c.get("lead") or not c.get("name"):
            raise ValueError(f"clock {cid!r}: needs a name, a full line and a lead")
    if sum(bool(c.get("shown")) for c in raw) > SHOWN_MAX:
        raise ValueError(f"at most {SHOWN_MAX} clocks may be shown")


@cache
def defs() -> tuple[dict, ...]:
    raw = tomllib.loads(_CLOCKS.read_text(encoding="utf-8"))["clock"]
    validate(raw)
    return tuple(raw)


def _district(text: str | None) -> str | None:
    d = _where(kuroshio(), text)[1]
    return d.name if d else None


def _state(session: Session, c: dict) -> dict:
    return session.clocks.setdefault(c["id"], {"filled": 0, "night": session.night, "rest_until": 0})


def _eased(c: dict, done: list[str]) -> bool:
    leads = c.get("eases_leads")
    return any(t == c["lead"] or (t in leads if leads else _district(t) in c["where"]) for t in done)


def tick(session: Session, rolls: list[dict], heat_rose: bool) -> None:
    """End of a player's turn: each clock moves at most one segment, up for its ticks, down for its eases."""
    now, here = _player_turns(session), _district(session.location)
    outcomes = {r.get("outcome") for r in rolls}
    done = [j["text"] for j in session.journal if j.get("kind") == "done" and j.get("turn") == now]
    for c in defs():
        s = _state(session, c)
        local = here in c["where"]
        fired = {"fight": local and (session.in_combat or any(r.get("skill") in _FIGHT_SKILLS for r in rolls)),
                 "miss": local and bool(outcomes & {"failure", "complication"}),
                 "heat": local and heat_rose,
                 "night": session.night > s["night"],
                 "lead_done": _eased(c, done)}
        s["night"] = session.night
        if now < s["rest_until"]:
            continue
        step = any(fired[t] for t in c["ticks"]) - any(fired[t] for t in c.get("eases", []))
        s["filled"] = max(0, s["filled"] + step)
        if step <= 0:
            continue
        if s["filled"] >= c["size"]:
            session.pending_world_events.append(c["full"])
            promises.add_lead(session, c["lead"])
            session.log.append(f"[pressure: {c['id']} full]")
            s["filled"], s["rest_until"] = 0, now + REST
        elif portent := c.get("portents", {}).get(str(s["filled"])):
            session.pending_world_events.append(portent)
            session.log.append(f"[pressure: {c['id']} {s['filled']}/{c['size']}]")


def line(session: Session) -> str:
    """"Pressure: Kuze-gumi squeeze on Ikebe Low 4/6." for shown clocks here above 0, else ""."""
    here = _district(session.location)
    bits = [f"{c['name']} {s['filled']}/{c['size']}" for c in defs()
            if c.get("shown") and here in c["where"] and (s := session.clocks.get(c["id"])) and s["filled"] > 0]
    return f"Pressure: {'; '.join(bits)}." if bits else ""


def view(session: Session) -> list[dict]:
    return [{"name": c["name"], "district": c["where"][0], "size": c["size"],
             "filled": session.clocks.get(c["id"], {}).get("filled", 0)} for c in defs() if c.get("shown")]
