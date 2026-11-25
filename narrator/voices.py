"""NPC voices (spec 2026-11-22-npc-voices-design.md): owner-approved sample lines, one shown per character per turn
with an engine-chosen move (Versu's selected speech-act), and type sheets for unnamed people (Valve's dynamic
dialogue: the most specific sheet wins). In-context demos get copied verbatim (arXiv 2402.09954), so one line a
turn, and server/narration.py cuts copies."""

import functools
import random
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from engine.session import Session
from narrator.world import World, _normalize, kuroshio

HEADER = "Voices this turn (how they sound; never repeat these lines word for word):"
_MAX_CHARACTERS, _MAX_TYPES, _SCAN_LINES = 3, 2, 6


@dataclass(frozen=True)
class Line:
    move: str
    text: str


@dataclass(frozen=True)
class Sheet:
    name: str
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class TypeSheet:
    name: str
    match: tuple[str, ...]
    voice: str
    lines: tuple[str, ...]
    exclude: tuple[str, ...] = ()  # named characters who replace this type when present


@dataclass(frozen=True)
class Voices:
    characters: dict[str, Sheet]
    types: tuple[TypeSheet, ...]


def load_voices(path: Path, world: World) -> Voices:
    raw = tomllib.loads(path.read_text())
    npcs = {n.name for n in world.npcs}
    characters = {}
    for c in raw.get("character", []):
        lines = tuple(Line(str(l["move"]), str(l["text"])) for l in c.get("lines", []))
        if c.get("name") not in npcs:
            raise ValueError(f"voice for {c.get('name')!r}, who is not a world npc")
        if len(lines) != 3 or len({l.move for l in lines}) != 3:
            raise ValueError(f"{c['name']!r} needs 3 lines with 3 different moves")
        characters[c["name"]] = Sheet(c["name"], lines)
    types = []
    for t in raw.get("type", []):
        if not t.get("match") or len(t.get("lines", [])) != 3:
            raise ValueError(f"type {t.get('name')!r} needs match words and 3 lines")
        types.append(TypeSheet(t["name"], tuple(_normalize(m) for m in t["match"]), t["voice"], tuple(t["lines"]),
                               tuple(t.get("exclude", ()))))
    return Voices(characters, tuple(types))


@functools.cache
def voices() -> Voices:
    return load_voices(Path(__file__).parent / "worlds" / "voices.toml", kuroshio())


def _mentioned_types(session: Session, action_text: str) -> list[TypeSheet]:
    """Types the action or the last few story lines mention, most recent first."""
    texts = [action_text, *reversed([l for l in session.log if not l.startswith("[")][-_SCAN_LINES:])]
    found: list[TypeSheet] = []
    for text in texts:
        t = _normalize(text)
        for sheet in voices().types:
            if sheet not in found and not set(sheet.exclude) & set(session.present) and any(re.search(rf"\b{re.escape(m)}\b", t) for m in sheet.match):
                found.append(sheet)
    return found[:_MAX_TYPES]


def _type_of(who: str) -> TypeSheet | None:
    who = _normalize(who)
    return next((t for t in voices().types if any(re.search(rf"\b{re.escape(m)}\b", who) for m in t.match)), None)


def voice_block(session: Session, action_text: str) -> str:
    """This turn's voices block, or "" when nobody with a sheet is here; records the moves and lines shown."""
    entries, shown = [], []
    copied = set(session.copied_lines)  # soak 17: a line copied once gets copied again, so it isn't shown again
    for name in [n for n in session.present if n in voices().characters][:_MAX_CHARACTERS]:
        sheet = voices().characters[name]
        moves = [l for l in sheet.lines if l.move != session.last_moves.get(name)]
        line = random.choice([l for l in moves if l.text not in copied] or moves)
        session.last_moves[name] = line.move
        if line.text in copied:
            entries.append(f"- {name} will {line.move}, in their own new words")
            continue
        entries.append(f'- {name} will {line.move}, like: "{line.text}"')
        shown.append(line.text)
    sheets = [(name, t) for name in [n for n in session.present if n in session.people][:_MAX_CHARACTERS]
              if (t := _type_of(session.people[name]["who"]))]
    for name, sheet in [*sheets, *((None, t) for t in _mentioned_types(session, action_text))]:
        n = session.type_turns.get(sheet.name, 0)
        step = next((i for i in range(len(sheet.lines)) if sheet.lines[(n + i) % len(sheet.lines)] not in copied), None)
        session.type_turns[sheet.name] = n + (step or 0) + 1  # past a skipped line, so the next turn shows a new one
        text = sheet.lines[(n + step) % len(sheet.lines)] if step is not None else None
        who = f"- {name}, a {sheet.name.lower()} ({sheet.voice})" if name else f"- A {sheet.name.lower()} ({sheet.voice})"
        entries.append(f'{who} sounds like: "{text}"' if text else f"{who}, in their own words")
        if text:
            shown.append(text)
    session.voice_lines = shown
    return "\n".join([HEADER, *entries]) if entries else ""
