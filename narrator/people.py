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
# Words that describe half the city: never enough on their own to say two walk-ons are one person.
_GENERIC = {"with", "that", "this", "from", "into", "their", "them", "person", "people", "someone", "guy", "woman",
            "young", "old", "man", "street", "stranger", "hand", "hands", "face", "coat", "jacket", "kid", "girl", "boy",
            "worker", "vendor", "driver", "local", "tall", "short", "thin", "burned", "scarred", "drunk", "angry"}


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


_NOT_ONE_PERSON = {"voice", "voices", "shadow", "shadows", "silhouette", "footsteps", "crowd", "crew", "gang"}


def one_person(who: str) -> bool:
    """Soak 2026-11-22: "A voice calls out from the shadows" and "security enforcers" became people. A voice or a
    shadow isn't someone you dealt with, and a group isn't one person."""
    head = re.findall(r"[a-z0-9āēīōū]+", re.split(r"\b(?:with|who|from|in|at|on|by)\b", who.lower())[0])
    return not (set(head) & _NOT_ONE_PERSON or (head and re.search(r"[^s]s$", head[-1])))


def grounded(session: Session, who: str, scene: str) -> bool:
    """The walk-on's head word ("dockworker" in "dockworker with a burned hand") is in the scene, and "who" isn't
    someone who already has a name (review 2026-11-22: "Old Hara" would become a second persona)."""
    said = set(re.findall(r"[a-z0-9āēīōū]+", scene.lower()))
    head = re.split(r"\b(?:with|who|from|in|at|on|by)\b", who.lower())[0]
    if not one_person(who):
        return False
    words = set(re.findall(r"[a-z0-9āēīōū]+", head)) - _GENERIC - {"a", "an", "the"}
    if not words:  # "man with sake breath" (soak 2026-11-22): a plain head, so its own details must be in the scene
        words = {w for w in re.findall(r"[a-z0-9āēīōū]+", who.lower()) if len(w) >= 4} - _GENERIC
    if not words:  # a bare "man" (soak 2026-11-24): nothing but the plain head is left, so the scene must say it
        words = set(re.findall(r"[a-z0-9āēīōū]+", head)) - {"a", "an", "the"}
    return bool(words & said) and not has_a_name(session, who)


_SOMEONE = {"him", "her", "them", "he", "she", "they", "guy", "man", "woman", "kid", "someone", "somebody", "stranger",
            "person"}


def dealt_with(who: str, action: str) -> bool:
    """The player's action is aimed at a person: it names "who" or refers to someone (soak 2026-11-22: the referee
    promoted a "noren curtain" on "I step off the Ring Line at Ikebe Low and look around.")."""
    did = set(re.findall(r"[a-z0-9āēīōū]+", action.lower()))
    named = {w for w in re.findall(r"[a-z0-9āēīōū]+", who.lower()) if len(w) >= 4} - _GENERIC
    return bool(did & (_SOMEONE | named))


def has_a_name(session: Session, who: str) -> bool:
    """ "who" names someone already known (a world NPC, a contact, someone on the roster, a player)."""
    known = {w for n in _taken(session) for w in re.findall(r"[a-z0-9āēīōū]+", n.lower()) if len(w) >= 3}
    return bool(set(re.findall(r"[a-z0-9āēīōū]+", who.lower())) & known)


def _district(session: Session) -> str | None:
    d = _where(kuroshio(), session.location)[1]
    return d.name if d else None


def _taken(session: Session) -> set[str]:
    contacts = {c["name"] for p in session.phone.values() for c in p.get("contacts", {}).values()}
    players = {c.name for c in session.characters.values()}
    return {*session.people, *session.npc_memory, *(n.name for n in kuroshio().npcs), *contacts, *players}


def _fresh_name(session: Session, district: str | None) -> str | None:
    taken = _taken(session)
    pools = [names().get(district or "", []), *names().values()]
    return next((n for pool in pools for n in pool if n not in taken), None)


def find(session: Session, who: str) -> str | None:
    """Someone on the roster from this district whose description shares a real word with this one."""
    here, words = _district(session), _words(who)
    scores = {n: len(words & _words(p["who"])) for n, p in session.people.items() if p["district"] == here}
    best = max(scores, key=scores.get, default=None)
    return best if best and scores[best] >= 1 and list(scores.values()).count(scores[best]) == 1 else None


def the_one_here(session: Session, action: str) -> str | None:
    """ "Help him up": a pronoun means the one walk-on already in the scene (soak 2026-11-24: the referee described
    Daisuke as "man with sharp eyes" the turn after "man with a blade", and he became a second person)."""
    if not re.search(r"\b(?:him|her|them)\b", action.lower()):
        return None
    here = [n for n in session.present if n in session.people]
    return here[0] if len(here) == 1 else None


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
            gone = min((n for n in session.people if n != name),
                       key=lambda n: (session.people[n]["weight"], session.people[n]["turn"]))
            promises.note(session, f"{gone}, the {session.people.pop(gone)['who']}", "lost touch")
            session.present = [n for n in session.present if n != gone]
    memory.remember(session, name, what, memory.NOTABLE)
    if name not in session.present:
        session.present.append(name)
    return name


def label(session: Session, name: str) -> str:
    """ "Goro (dockworker with a burned hand)" for a person, else the name."""
    p = session.people.get(name)
    return f"{name} ({p['who']})" if p else name


def comeback(session: Session) -> str | None:
    """Who returns: this district's people first, then anyone, weighted by how much they matter; not twice in 20."""
    now = _player_turns(session)
    # Not someone standing right here, and not someone just met (review 2026-11-22).
    ready = [n for n, p in session.people.items() if n not in session.present and now - p["turn"] >= RETURN_GAP
             and (p["returned"] is None or now - p["returned"] >= RETURN_GAP)]
    here = [n for n in ready if session.people[n]["district"] == _district(session)]
    pool = here or ready
    if not pool:
        return None
    return random.choices(pool, weights=[session.people[n]["weight"] for n in pool])[0]
