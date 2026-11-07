"""Approved place art for the play screen: the current location -> a play-sized JPG of that place.

The JPGs in worlds/place_art/ are made by tools/export_place_art.py from the approved place designs. A location
matches a place by the design's name or, when the world bible has the same place, any of its names and aliases.
The longest match wins, so "Mama Sato's izakaya, Ikebe Low" shows the izakaya, not the district.
"""

import functools
import re
import tomllib
from pathlib import Path

from narrator.world import _normalize, kuroshio

ART_DIR = Path(__file__).parent / "worlds" / "place_art"
_DESIGNS = Path(__file__).parent / "worlds" / "designs"


def _slugs() -> list[str]:
    return sorted(p.stem for p in ART_DIR.glob("*.jpg"))


def design_name(slug: str) -> str | None:
    path = _DESIGNS / f"{slug}.toml"
    if not path.exists():
        return None
    d = tomllib.loads(path.read_text())
    return d["name"] if d.get("status") == "approved" and d.get("kind") != "character" else None


@functools.cache
def _world_names() -> list[tuple[str, ...]]:
    world = kuroshio()
    return [tuple(_normalize(n) for n in (e.name, *e.aliases)) for e in world.districts + world.places]


# Last words too plain to stand for one place on their own ("the room", "a house").
_GENERIC = {"room", "house", "box", "block", "low", "line", "heights", "loop", "docks", "cho"}


def _last_words(slugs: tuple[str, ...]) -> dict[str, str]:
    """A design's last word, when no other design ends with it and it isn't generic: "izakaya" -> Mama Sato's
    izakaya (dry run 2026-11-06: the narrator shortened the location and the art disappeared)."""
    last: dict[str, list[str]] = {}
    for slug in slugs:
        name = design_name(slug)
        if name:
            last.setdefault(_normalize(name).replace("-", " ").split()[-1], []).append(slug)
    return {word: found[0] for word, found in last.items() if len(found) == 1 and word not in _GENERIC}


def _keys(slugs: tuple[str, ...]) -> list[tuple[str, str]]:
    keys = [(word, slug) for word, slug in _last_words(slugs).items()]
    for slug in slugs:
        name = design_name(slug)
        if not name:
            continue
        names = {_normalize(name)}
        for entry in _world_names():
            if _normalize(name) in entry:
                names.update(entry)
        keys += [(n, slug) for n in names]
    # World places with a kept render saved under their own name (owner Keep, World Gallery 2026-11-06/07).
    for entry in kuroshio().places:
        slug = re.sub(r"[^a-z0-9]+", "-", _normalize(entry.name)).strip("-")
        if slug in slugs:
            keys += [(_normalize(n), slug) for n in (entry.name, *entry.aliases)]
    return sorted(keys, key=lambda k: -len(k[0]))


def location_art(location: str | None) -> str | None:
    if not location:
        return None
    loc = _normalize(location)
    for key, slug in _keys(tuple(_slugs())):
        if re.search(rf"\b{re.escape(key)}\b", loc):
            return f"place-art/{slug}.jpg"
    return None


def district_art(location: str | None) -> Path | None:
    """The approved art of the district a place is in, to start a new image from when the place itself has none
    (owner 2026-11-07: the Ring Line train car started from the Ring Line art kept Kuroshio's look)."""
    from narrator.world import _where  # late: world imports nothing from here, but keep the module light
    _, district = _where(kuroshio(), location)
    art = location_art(district.name) if district else None
    return ART_DIR / Path(art).name if art else None
