"""The night clock (spec 2026-11-23-night-clock-design.md): five stretches a night, told by the city's rhythm, owned by
the engine (Song, Zhu & Callison-Burch 2024: state the engine controls stays consistent). The day passes off-screen."""
import functools
import re
import tomllib
from pathlib import Path

from engine.session import Session
from narrator.cast import _named, _player_turns
from narrator.world import _where, kuroshio

STRETCHES = {
    "evening": "the city filling up, shops and stalls open",
    "last train": "the last Ring Line trains; people heading home or heading out",
    "shutters down": "shops shut; izakaya and the illegal places still open",
    "small hours": "empty streets, only night people",
    "first train": "the first trains; the night giving out",
}
ORDER = list(STRETCHES)
TURNS = 3  # rounds per stretch (a round is one turn each): about 15 a night, however big the party
NO_TRAINS = {"shutters down", "small hours"}
DAYBREAK = "The sky greys, the city shutters for the day, and the next night comes on."
_HOURS_PATH = Path(__file__).parent / "worlds" / "hours.toml"


@functools.cache
def _asleep_table() -> dict[str, tuple[str, ...]]:
    with _HOURS_PATH.open("rb") as f:
        table = {name: tuple(s) for name, s in tomllib.load(f)["asleep"].items()}
    for name, stretches in table.items():
        if set(stretches) - set(STRETCHES) or set(stretches) == set(STRETCHES):
            raise ValueError(f"hours.toml: {name} has an unknown stretch, or sleeps all night, in {stretches}")
    return table


@functools.cache
def _where_table() -> dict[str, dict[str, str]]:
    """Spec 2026-11-23-whereabouts: an NPC's place in some stretches (Stardew keeps schedules as data, with a default)."""
    with _HOURS_PATH.open("rb") as f:
        table = tomllib.load(f).get("where", {})
    places = {p.name for p in kuroshio().places}
    npcs = {n.name for n in kuroshio().npcs}
    for name, slots in table.items():
        if name not in npcs or set(slots) - set(STRETCHES) or set(slots.values()) - places:
            raise ValueError(f"hours.toml: [where.{name!r}] needs a world NPC, known stretches and place cards: {slots}")
    return table


def stretch(session: Session) -> str:
    return ORDER[session.stretch]


def asleep(session: Session, name: str) -> bool:
    return stretch(session) in _asleep_table().get(name, ())


def where(session: Session, name: str) -> str | None:
    """The place card someone is at this stretch, or None: where they always are (their venue, or nowhere fixed)."""
    return _where_table().get(name, {}).get(stretch(session))


def scheduled_here(session: Session) -> list[str]:
    place = _where(kuroshio(), session.location)[0]  # the world's own place matching, aliases included
    return [n for n in _where_table() if place and where(session, n) == place.name]


def elsewhere(session: Session, name: str) -> bool:
    """Scheduled at some other place right now, so not at their own venue."""
    return bool(where(session, name)) and name not in scheduled_here(session)


def whereabouts(session: Session, action: str) -> str | None:
    """Asking around: "where" plus a scheduled NPC's name tells the narrator where they usually are, now and next."""
    if not re.search(r"\bwhere\b", action, re.I):
        return None
    lines = []
    asked = set(_named(action))  # whole names and aliases: "tomorrow" is not Moro (review 2026-11-23)
    for name, slots in _where_table().items():
        if name not in asked:
            continue
        for s in (ORDER[session.stretch], ORDER[(session.stretch + 1) % len(ORDER)]):
            if s in slots:
                lines.append(f"{name} is usually at the {slots[s]} in the {s}")
    return ("If asked: " + "; ".join(lines) + ".") if lines else None


def _district(session: Session) -> str | None:
    d = _where(kuroshio(), session.location)[1]
    return d.name if d else None


def _rounds(session: Session) -> int:
    """Owner's call 2026-11-23: a party of 3 must not burn a stretch every round, so time counts rounds, not turns."""
    return _player_turns(session) // max(1, len(session.characters))


def _next(session: Session) -> None:
    if session.stretch == len(ORDER) - 1:
        session.night += 1
        session.stretch = 0
        session.pending_world_events.append(DAYBREAK)
    else:
        session.stretch += 1
    session.log.append(f"[clock: night {session.night}, {stretch(session)}]")


def tick(session: Session) -> None:
    """End of a player's turn: every TURNS turns, and each ride to another district, moves the night on one stretch."""
    now, here = _rounds(session), _district(session)
    if session.stretch_start is None:  # a save from before the clock starts its stretch now, not 3 turns ago
        session.stretch_start = now
    rode = bool(here and session.clock_district and here != session.clock_district)
    session.clock_district = here or session.clock_district
    steps = rode + (now - session.stretch_start >= TURNS)
    for _ in range(steps):
        _next(session)
    if steps:
        session.stretch_start = now


def sleep(session: Session, player_id: str) -> None:
    """Sleep always works (Disco Elysium players get stuck when it doesn't): the next night's evening, once the whole
    party sleeps (owner's call 2026-11-23); until then the sleeper just rests."""
    session.sleepers = sorted({*session.sleepers, player_id})
    if set(session.characters) - set(session.sleepers):
        session.log.append(f"[clock: {session.characters[player_id].name} sleeps; the night goes on until everyone does]")
        return
    session.sleepers = []
    session.night += 1
    session.stretch = 0
    session.stretch_start = _rounds(session)
    session.clock_district = _district(session) or session.clock_district
    session.log.append(f"[clock: slept; night {session.night}, evening]")


# The player's own wait, not "I can't wait to..." or "tell her to wait" (review 2026-11-23).
_WAIT = re.compile(r"\bI\s+(?:\w+\s+){0,2}?(wait|kill time|pass the time|lie low)\b", re.I)
_NOT = re.compile(r"\b(can't|cannot|can not|don't|do not|won't|will not|not)\s+(wait|kill|pass|lie)\b", re.I)
# A bare wait skips an hour only when it says so: "I wait for her answer" is a moment, not a stretch.
_A_WHILE = re.compile(r"kill(ing)? time|pass(ing)? the time|lie low|a while|an hour|it out|until later", re.I)
_ALIASES = {"dawn": "first train", "morning": "first train", "midnight": "last train", "shutters": "shutters down"}
_WORDS = {s: s for s in ORDER} | _ALIASES
_UNTIL = re.compile(r"\b(?:until|till|for|through)\s+(?:the\s+)?(" + "|".join(sorted(_WORDS, key=len, reverse=True))
                    + r")\b", re.I)


def wait(session: Session, action: str) -> str | None:
    """A wait skips to a named stretch's start (or one stretch); a past stretch means the next night's. Refused in a
    fight, with the reason told (Skyrim players hate refusals they can't see the cause of). Returns the narrator note."""
    if not _WAIT.search(action) or _NOT.search(action):
        return None
    named = _UNTIL.search(action)
    if not named and not _A_WHILE.search(action):
        return None
    if session.in_combat:
        return "No waiting: there's a fight on. Say so in the story."
    target = ORDER.index(_WORDS[named[1].lower()]) if named else (session.stretch + 1) % len(ORDER)
    for _ in range((target - session.stretch) % len(ORDER) or len(ORDER)):
        _next(session)
    session.stretch_start = _rounds(session)
    session.clock_district = _district(session) or session.clock_district  # a ride this turn is part of the wait
    session.cast_location = None  # who is here changes with the hour: the cast is rebuilt for the new stretch
    return f"You waited until {stretch(session)}: tell the wait in one sentence, then the new hour."


def line(session: Session) -> str:
    """The narrator's one time line, late in the prompt next to the world event."""
    now = stretch(session)
    text = f"Time: night {session.night}, {now} ({STRETCHES[now]})."
    if now in NO_TRAINS:
        text += " No Ring Line trains now: walking, or a paid taxi."
    sleeping = [n for n in _asleep_table() if now in _asleep_table()[n]]
    if sleeping:
        text += " Asleep or shut now: " + ", ".join(sleeping) + "."
    return text
