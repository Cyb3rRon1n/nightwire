"""The night clock (spec 2026-11-23-night-clock-design.md): five stretches a night, told by the city's rhythm, owned by
the engine (Song, Zhu & Callison-Burch 2024: state the engine controls stays consistent). The day passes off-screen."""
import functools
import tomllib
from pathlib import Path

from engine.session import Session
from narrator.cast import _player_turns
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


def stretch(session: Session) -> str:
    return ORDER[session.stretch]


def asleep(session: Session, name: str) -> bool:
    return stretch(session) in _asleep_table().get(name, ())


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
