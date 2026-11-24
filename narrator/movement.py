"""Where the player is: the engine decides from the action, the referee's guess is only a fallback.

Comparable systems keep location in code and let the model only propose it (PAYADOR; the Labyrinth AI GM paper);
soak run 5 (2026-11-07) lost two moves to narrator timeouts, and the stale Scene line then held the narrator in
Old Hara's clinic for 11 turns. Known places = world districts and places (with aliases) + approved place designs.
"""

import functools
import re

from narrator.place_art import _last_words, _slugs, design_name
from narrator.world import _normalize, kuroshio

# "I head to", "I take the Ring Line to", "I walk back toward": a movement verb, then the place after it.
_MOVE = re.compile(r"\b(?:go|goes|going|head|heads|heading|walk|walks|run|runs|drive|ride|rides|travel|return|returns"
                   r"|enter|enters|follow|follows|step (?:into|inside)|make (?:my|our|his|her|their) way|take the (?:ring|yomi) line|(?:take|takes|catch|catches|hail|hails) (?:a|the) (?:taxi|cab))\b")
_TOWARD = re.compile(r"\b(?:to|toward|towards|into|for)\b")


def _norm(text: str) -> str:
    return _normalize(text).replace("’", "'")


@functools.cache
def _keys() -> list[tuple[str, str]]:
    """(normalized name or alias, canonical name), longest first."""
    world = kuroshio()
    keys = [(_norm(n), e.name) for e in world.districts + world.places for n in (e.name, *e.aliases)]
    slugs = tuple(_slugs())
    for slug in slugs:
        name = design_name(slug)
        if name and _norm(name) not in {k for k, _ in keys}:
            keys.append((_norm(name), name))
    keys += [(word, design_name(slug)) for word, slug in _last_words(slugs).items()]  # "the izakaya"
    return sorted(set(keys), key=lambda k: -len(k[0]))


# Place names that are also everyday words: in the model's prose they count only capitalised. The Ring Line's own
# card calls it "the commuter loop", and soak run 2026-11-18 drifted to The Loop from a train scene.
_EVERYDAY = {"loop": "Loop"}


def _named(key: str, t: str, raw: str, cased: bool) -> bool:
    if not re.search(rf"(?<!\w){re.escape(key)}(?!\w)", t):
        return False
    word = _EVERYDAY.get(key.removeprefix("the "))
    return not (cased and word) or re.search(rf"(?<!\w){word}(?!\w)", raw) is not None


def known_place(text: str | None, cased: bool = True) -> str | None:
    """The known place named in the text, longest name first ("Ikebe Low - Old Hara's clinic" -> the clinic).
    cased=False for a player's typed move, where "the loop" means the place."""
    raw = text or ""
    t = _norm(raw)
    return next((name for key, name in _keys() if _named(key, t, raw, cased)), None)


def places_in(text: str | None) -> set[str]:
    """Every known place the text names, by any of its names ("the izakaya" -> Mama Sato's izakaya)."""
    raw = text or ""
    t = _norm(raw)
    return {name for key, name in _keys() if _named(key, t, raw, True)}


def destination(action: str) -> str | None:
    """The known place the action moves the player to, or None when it doesn't clearly move them."""
    t = _norm(action)
    move = _MOVE.search(t)
    if not move:
        return None
    tail = t[move.end():]
    toward = _TOWARD.search(tail)
    return known_place(tail[toward.end():] if toward else tail, cased=False)


# "I ask Old Hara", "I talk to Mama Sato": addressing someone who runs a place, from somewhere else.
_ADDRESS = re.compile(r"\b(?:ask|asks|tell|tells|talk(?:s)? (?:to|with)|speak(?:s)? (?:to|with)|greet|greets|visit|"
                      r"visits|show|shows|pay|pays|thank|thanks)\s+((?:\S+\s+){0,2}\S+)")


def visit(action: str, location: str | None) -> str | None:
    """The place of the keeper the action addresses, when the player is elsewhere: a tabletop GM's "you head over
    to the clinic". Soaks 2026-11-21 turn 13 (twice): "I ask Old Hara about my optics" from the izakaya had the
    narrator walk Rin into the clinic, but the game never moved her."""
    from narrator.world import _mentions, _venues  # world -> place_art -> movement would loop at import time

    if not location:
        return None
    address = _ADDRESS.search(_norm(action))
    if not address:
        return None
    world = kuroshio()
    keeper = next((n for n in world.npcs if _mentions(n, address.group(1))), None)
    venue = _venues(world).get(keeper.name) if keeper else None
    if not venue or venue.lower() in location.lower():
        return None
    return known_place(venue, cased=False)
