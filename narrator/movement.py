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
                   r"|enter|enters|step (?:into|inside)|make (?:my|our|his|her|their) way|take the (?:ring|yomi) line)\b")
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


def known_place(text: str | None) -> str | None:
    """The known place named in the text, longest name first ("Ikebe Low - Old Hara's clinic" -> the clinic)."""
    t = _norm(text or "")
    return next((name for key, name in _keys() if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", t)), None)


def destination(action: str) -> str | None:
    """The known place the action moves the player to, or None when it doesn't clearly move them."""
    t = _norm(action)
    move = _MOVE.search(t)
    if not move:
        return None
    tail = t[move.end():]
    toward = _TOWARD.search(tail)
    return known_place(tail[toward.end():] if toward else tail)
