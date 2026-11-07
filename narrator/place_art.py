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


def _keys(slugs: tuple[str, ...]) -> list[tuple[str, str]]:
    keys = []
    for slug in slugs:
        name = design_name(slug)
        if not name:
            continue
        names = {_normalize(name)}
        for entry in _world_names():
            if _normalize(name) in entry:
                names.update(entry)
        keys += [(n, slug) for n in names]
    return sorted(keys, key=lambda k: -len(k[0]))


def location_art(location: str | None) -> str | None:
    if not location:
        return None
    loc = _normalize(location)
    for key, slug in _keys(tuple(_slugs())):
        if re.search(rf"\b{re.escape(key)}\b", loc):
            return f"place-art/{slug}.jpg"
    return None
