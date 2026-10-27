"""Nightwire's world bible: an always-on primer plus district/faction/NPC cards
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
_MAX_SYSTEM_BLOCK_CHARS = 1900
_MAX_CARDS = 4
_SCAN_LINES = 6


@dataclass(frozen=True)
class WorldEntry:
    name: str
    aliases: tuple[str, ...]
    card: str
    # NPCs only: the district they live in (an existing district name).
    home: str | None = None


@dataclass(frozen=True)
class World:
    primer: str
    glossary: dict[str, str]
    districts: tuple[WorldEntry, ...]
    factions: tuple[WorldEntry, ...]
    npcs: tuple[WorldEntry, ...] = ()

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
        aliases = item.get("aliases", [])
        # An empty alias would compile to \b\b and match every text.
        if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
            raise ValueError(f"world {kind} {item['name']!r} aliases must be a list of non-empty strings")
        home = item.get("home")
        if home is not None and (not isinstance(home, str) or not home.strip()):
            raise ValueError(f"world {kind} {item['name']!r} home must be a district name")
        entries.append(WorldEntry(item["name"], tuple(aliases), card, home))
    return tuple(entries)


def parse_world(raw: dict) -> World:
    primer = raw.get("primer")
    if not isinstance(primer, str) or not primer.strip():
        raise ValueError("world is missing 'primer'")
    world = World(
        primer.strip(),
        dict(raw.get("glossary", {})),
        _entries(raw, "district"),
        _entries(raw, "faction"),
        _entries(raw, "npc"),
    )
    block_len = len(world.system_block())
    if block_len > _MAX_SYSTEM_BLOCK_CHARS:
        raise ValueError(f"world primer + glossary is {block_len} chars (max {_MAX_SYSTEM_BLOCK_CHARS})")
    district_names = {d.name for d in world.districts}
    for npc in world.npcs:
        if npc.home is not None and npc.home not in district_names:
            raise ValueError(f"world npc {npc.name!r} home {npc.home!r} is not a district")
    seen: dict[str, str] = {}
    for entry in world.districts + world.factions + world.npcs:
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
    """Cards for this turn, in priority order: the current location's district;
    then one NPC who lives there (skipped if a local NPC is already mentioned);
    then districts/factions/NPCs mentioned in the action or recent narrative,
    most recent first. Capped by count and by budget_chars."""
    location = _normalize(session.location or "")
    district = next((d for d in world.districts if location and _mentions(d, location)), None)
    # [image: ...]-style lines are UI annotations, not narrative (same filter
    # server/narration.py applies).
    narrative = [line for line in session.log if not line.startswith("[")][-_SCAN_LINES:]
    mentions: list[WorldEntry] = []
    for text in (action_text, *reversed(narrative)):
        normalized = _normalize(text)
        for entry in world.districts + world.factions + world.npcs:
            if entry is not district and entry not in mentions and _mentions(entry, normalized):
                mentions.append(entry)
    # Put someone on stage even when nobody was named, ahead of older mentions
    # so stale faction chatter can't crowd them out of the card cap.
    # ponytail: first resident in file order always wins; rotate or pick the
    # least-recently-shown resident if scenes start to feel samey.
    # One local face per scene: skip if a local NPC is already mentioned.
    resident = None
    if district and not any(e.home == district.name for e in mentions):
        resident = next((n for n in world.npcs if n.home == district.name), None)
    ordered = [e for e in (district, resident) if e] + mentions
    cards: list[str] = []
    total = 0
    for entry in ordered[:_MAX_CARDS]:
        total += len(entry.card) + 1
        if total > budget_chars:
            break
        cards.append(entry.card)
    return cards
