"""Emerging characters: an unnamed walk-on the player deals with directly gets a name from the district's list, joins
the cast, remembers what happened, and can come back (Starforged's connections, Mythic's weighted Characters List,
Shadow of Mordor's Nemesis). See docs/superpowers/specs/2026-11-22-emerging-characters-design.md."""

import random
import re
import tomllib
from functools import cache
from pathlib import Path

from engine.session import Session
from narrator import memory, promises
from narrator.cast import _player_turns
from narrator.world import _where, kuroshio

MAX_PEOPLE, MAX_WEIGHT, RETURN_GAP = 12, 3, 20
_WHO_MAX, _WHAT_MAX = 40, 80
_GENERIC = {"with", "that", "this", "from", "into", "their", "them", "person", "people", "someone", "guy", "woman",
            "young", "old", "man"}


@cache
def names() -> dict[str, list[str]]:
    return tomllib.loads((Path(__file__).parent / "worlds" / "names.toml").read_text(encoding="utf-8"))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9āēīōū]+", text.lower()) if len(w) >= 4 and w not in _GENERIC}


def split(answer: str) -> tuple[str, str] | None:
    """ "dockworker with a burned hand: Rin helped him lift a crate" -> (who, what)."""
    who, sep, what = answer.partition(":")
    who, what = promises._cap(" ".join(who.split()), _WHO_MAX), promises._cap(" ".join(what.split()), _WHAT_MAX)
    return (who, what) if sep and who and what else None


def grounded(who: str, scene: str) -> bool:
    """A real word of "who" is in the scene (the referee can't invent a person)."""
    return bool(_words(who) & set(re.findall(r"[a-z0-9āēīōū]+", scene.lower())))


def _district(session: Session) -> str | None:
    d = _where(kuroshio(), session.location)[1]
    return d.name if d else None


def _taken(session: Session) -> set[str]:
    return {*session.people, *session.npc_memory, *(n.name for n in kuroshio().npcs)}


def _fresh_name(session: Session, district: str | None) -> str | None:
    taken = _taken(session)
    pools = [names().get(district or "", []), *names().values()]
    return next((n for pool in pools for n in pool if n not in taken), None)


def find(session: Session, who: str) -> str | None:
    """Someone on the roster from this district whose description shares a real word with this one."""
    here, words = _district(session), _words(who)
    return next((n for n, p in session.people.items() if p["district"] == here and words & _words(p["who"])), None)


def meet(session: Session, who: str, what: str) -> str | None:
    """A walk-on the player dealt with: raise an existing person's weight, or name a new one. Returns the name."""
    now = _player_turns(session)
    name = find(session, who)
    if name:
        p = session.people[name]
        p.update(weight=min(MAX_WEIGHT, p["weight"] + 1), turn=now, what=what)
    else:
        district = _district(session)
        name = _fresh_name(session, district)
        if name is None:
            return None
        session.people[name] = {"who": who, "what": what, "district": district, "place": session.location,
                                "turn": now, "weight": 1, "returned": None}
        session.log.append(f"[person: {name} = {who}]")
        while len(session.people) > MAX_PEOPLE:
            gone = min(session.people, key=lambda n: (session.people[n]["weight"], session.people[n]["turn"]))
            promises.note(session, f"{gone}, the {session.people.pop(gone)['who']}", "lost touch")
    memory.remember(session, name, what, memory.NOTABLE)
    if name not in session.present:
        session.present.append(name)
    return name


def label(session: Session, name: str) -> str:
    """ "Goro (dockworker with a burned hand)" for a person, else the name."""
    p = session.people.get(name)
    return f"{name} ({p['who']})" if p else name


def mentioned(session: Session, text: str) -> list[str]:
    words = set(re.findall(r"[a-z0-9āēīōū]+", text.lower()))
    return [n for n in session.people if n.lower() in words]


def comeback(session: Session) -> str | None:
    """Who returns: this district's people first, then anyone, weighted by how much they matter; not twice in 20."""
    now = _player_turns(session)
    ready = [n for n, p in session.people.items() if p["returned"] is None or now - p["returned"] >= RETURN_GAP]
    here = [n for n in ready if session.people[n]["district"] == _district(session)]
    pool = here or ready
    if not pool:
        return None
    return random.choices(pool, weights=[session.people[n]["weight"] for n in pool])[0]
