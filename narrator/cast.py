"""Who is in the scene. Nothing tracked it, so anyone mentioned lately counted as here (soak 2026-11-19 turn 28:
Mama Sato spoke to Rin as she woke up). A tabletop GM keeps the scene's cast the same way; SillyTavern group chats
let only active members speak. On a move everyone stays behind except the place's keeper and whoever the action
names; an NPC joins when the story has them speak or names them."""

import re

from engine.session import Session
from narrator.world import _mentions, _normalize, _venues, kuroshio

# Someone who runs a place stays in it, but steps out now and then (owner 2026-11-21: "eventually or special events
# where person leaves their place. keeps it immersive"): one drop-in elsewhere per this many player turns.
_DROP_IN_EVERY = 12


def _named(text: str, session: Session | None = None) -> list[str]:
    """World NPCs, and the player's recurring people (narrator/people.py) by their name, mentioned in the text."""
    t = _normalize(text)
    # Capitalised, as names are written: "Shin" is the person, "his shin" is not (review 2026-11-22).
    people = [n for n in (session.people if session else {}) if re.search(rf"\b{re.escape(n)}\b", text)]
    return [n.name for n in kuroshio().npcs if _mentions(n, t)] + people


def _away_keepers(session: Session) -> set[str]:
    """Who runs a place that isn't where the player is: Mama Sato anywhere but her izakaya."""
    if not session.location:
        return set()  # nowhere known yet (the first turn): nobody is away
    here = session.location.lower()
    return {name for name, venue in _venues(kuroshio()).items() if venue.lower() not in here}


def _player_turns(session: Session) -> int:
    actors = tuple(f"{pid}: " for pid in session.characters)
    return sum(line.startswith(actors) for line in session.log) if actors else 0


def refresh(session: Session, action_text: str) -> None:
    """Resets the cast when the player is somewhere new. A keeper away from their place goes back to it unless the
    action names them (soak 2026-11-21: Mama Sato walked out with Rin and stayed by her side for 20 turns)."""
    from narrator import clock  # clock counts turns with this module's _player_turns
    named = _named(action_text, session)
    if session.location != session.cast_location:
        # The night clock: a keeper asleep or scheduled elsewhere isn't there when you arrive; anyone scheduled here
        # now is (spec 2026-11-23-whereabouts); someone the action names still is.
        keeper = [n for n in _named(session.location or "") if not clock.asleep(session, n)
                  and not clock.elsewhere(session, n)]
        session.present = list(dict.fromkeys([*keeper, *clock.scheduled_here(session), *named]))
        session.cast_location = session.location
    # A scheduled keeper already on stage stays until the player leaves, even when their stretch ends (review).
    away = _away_keepers(session) - set(named) - set(clock.scheduled_here(session)) \
        - (set(session.present) & set(clock._where_table()))
    session.present = [name for name in session.present if name not in away]


def keep_away_keepers(session: Session, lines: list[tuple]) -> list[tuple]:
    """(speaker, anything) pairs minus lines by a keeper away from their place, unless the cast already has them or
    it is time for a rare drop-in. Never empties the turn."""
    away = _away_keepers(session) - set(session.present)
    def is_away(speaker: str) -> bool:
        return bool(away.intersection(_named(speaker)))

    if not any(is_away(speaker) for speaker, _ in lines):
        return lines
    turn = _player_turns(session)
    if turn - (session.drop_in_turn or 0) >= _DROP_IN_EVERY:  # the first one waits too
        session.drop_in_turn = turn
        return lines
    kept = [line for line in lines if not is_away(line[0])]
    return kept or lines


def note(session: Session, lines: list[tuple[str, str]]) -> None:
    """(speaker, text) pairs from this turn's story: speakers and NPCs the narrator names join the cast."""
    # ponytail: a name in the prose counts as on stage, so "nobody has seen Hara in weeks" adds him; a judge call
    # could tell talk-about from presence if that shows up in soaks.
    for speaker, text in lines:
        for name in _named(text if speaker == "narrator" else speaker, session):
            if name not in session.present:
                session.present.append(name)


def present_line(session: Session) -> str:
    labels = [f"{n} ({session.people[n]['who']})" if n in session.people else n for n in session.present]
    who = ", ".join(labels) or "no named characters"
    return f"Present: {who}. Anyone else must arrive on screen first."
