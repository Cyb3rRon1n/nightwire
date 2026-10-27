"""Nightwire's world bible: an always-on primer plus district/faction cards
selected per turn - see docs/superpowers/specs/2026-10-26-world-bible-design.md."""

import functools
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from engine.session import Session

_KUROSHIO_PATH = Path(__file__).parent / "worlds" / "kuroshio.toml"
# Heuristic sizes for an 8B narrator (no published authoritative numbers -
# see the spec's research section); live verification is the real check.
_MAX_CARD_CHARS = 400
_MAX_SYSTEM_BLOCK_CHARS = 1600
_MAX_CARDS = 4
_SCAN_LINES = 6


@dataclass(frozen=True)
class WorldEntry:
    name: str
    aliases: tuple[str, ...]
    card: str


@dataclass(frozen=True)
class World:
    primer: str
    glossary: dict[str, str]
    districts: tuple[WorldEntry, ...]
    factions: tuple[WorldEntry, ...]

    def system_block(self) -> str:
        terms = "\n".join(f"{term}: {definition}" for term, definition in self.glossary.items())
        return f"{self.primer}\nGlossary:\n{terms}"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _entries(raw: dict, kind: str) -> tuple[WorldEntry, ...]:
    entries = []
    for item in raw.get(kind, []):
        for key in ("name", "card"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"world {kind} entry {item.get('name', item)!r} is missing '{key}'")
        card = item["card"].strip()
        if len(card) > _MAX_CARD_CHARS:
            raise ValueError(f"world {kind} {item['name']!r} card is {len(card)} chars (max {_MAX_CARD_CHARS})")
        entries.append(WorldEntry(item["name"], tuple(item.get("aliases", [])), card))
    return tuple(entries)


def parse_world(raw: dict) -> World:
    primer = raw.get("primer")
    if not isinstance(primer, str) or not primer.strip():
        raise ValueError("world is missing 'primer'")
    world = World(primer.strip(), dict(raw.get("glossary", {})), _entries(raw, "district"), _entries(raw, "faction"))
    block_len = len(world.system_block())
    if block_len > _MAX_SYSTEM_BLOCK_CHARS:
        raise ValueError(f"world primer + glossary is {block_len} chars (max {_MAX_SYSTEM_BLOCK_CHARS})")
    seen: dict[str, str] = {}
    for entry in world.districts + world.factions:
        for key in (entry.name, *entry.aliases):
            normalized = _normalize(key)
            if normalized in seen:
                raise ValueError(f"world name/alias {key!r} ({entry.name}) duplicates one used by {seen[normalized]}")
            seen[normalized] = entry.name
    return world


def load_world(path: Path) -> World:
    with path.open("rb") as f:
        return parse_world(tomllib.load(f))


@functools.cache
def kuroshio() -> World:
    return load_world(_KUROSHIO_PATH)


def _mentions(entry: WorldEntry, normalized_text: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(_normalize(key))}\b", normalized_text)
        for key in (entry.name, *entry.aliases)
    )


def select_cards(world: World, session: Session, action_text: str, budget_chars: int) -> list[str]:
    """Cards for this turn: the current location's district first, then
    districts/factions mentioned in the action or recent narrative, most
    recent first. Capped by count and by budget_chars."""
    ordered: list[WorldEntry] = []
    location = _normalize(session.location or "")
    if location:
        ordered += [d for d in world.districts if _mentions(d, location)][:1]
    # [image: ...]-style lines are UI annotations, not narrative (same filter
    # server/narration.py applies).
    narrative = [line for line in session.log if not line.startswith("[")][-_SCAN_LINES:]
    for text in (action_text, *reversed(narrative)):
        normalized = _normalize(text)
        for entry in world.districts + world.factions:
            if entry not in ordered and _mentions(entry, normalized):
                ordered.append(entry)
    cards: list[str] = []
    total = 0
    for entry in ordered[:_MAX_CARDS]:
        total += len(entry.card) + 1
        if total > budget_chars:
            break
        cards.append(entry.card)
    return cards
