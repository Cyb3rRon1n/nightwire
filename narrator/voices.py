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
        types.append(TypeSheet(t["name"], tuple(_normalize(m) for m in t["match"]), t["voice"], tuple(t["lines"])))
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
            if sheet not in found and any(re.search(rf"\b{re.escape(m)}\b", t) for m in sheet.match):
                found.append(sheet)
    return found[:_MAX_TYPES]


def voice_block(session: Session, action_text: str) -> str:
    """This turn's voices block, or "" when nobody with a sheet is here; records the moves and lines shown."""
    entries, shown = [], []
    for name in [n for n in session.present if n in voices().characters][:_MAX_CHARACTERS]:
        sheet = voices().characters[name]
        line = random.choice([l for l in sheet.lines if l.move != session.last_moves.get(name)])
        session.last_moves[name] = line.move
        entries.append(f'- {name} will {line.move}, like: "{line.text}"')
        shown.append(line.text)
    for sheet in _mentioned_types(session, action_text):
        n = session.type_turns.get(sheet.name, 0)
        session.type_turns[sheet.name] = n + 1
        text = sheet.lines[n % len(sheet.lines)]
        entries.append(f'- A {sheet.name.lower()} ({sheet.voice}) sounds like: "{text}"')
        shown.append(text)
    session.voice_lines = shown
    return "\n".join([HEADER, *entries]) if entries else ""
