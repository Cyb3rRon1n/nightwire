"""Who is in the scene. Nothing tracked it, so anyone mentioned lately counted as here (soak 2026-11-19 turn 28:
Mama Sato spoke to Rin as she woke up). A tabletop GM keeps the scene's cast the same way; SillyTavern group chats
let only active members speak. On a move everyone stays behind except the place's keeper and whoever the action
names; an NPC joins when the story has them speak or names them."""

from engine.session import Session
from narrator.world import _mentions, _normalize, kuroshio


def _named(text: str) -> list[str]:
    t = _normalize(text)
    return [n.name for n in kuroshio().npcs if _mentions(n, t)]


def refresh(session: Session, action_text: str) -> None:
    """Resets the cast when the player is somewhere new."""
    if session.location == session.cast_location:
        return
    keeper = _named(session.location or "")  # Mama Sato in Mama Sato's izakaya
    session.present = list(dict.fromkeys([*keeper, *_named(action_text)]))
    session.cast_location = session.location


def note(session: Session, lines: list[tuple[str, str]]) -> None:
    """(speaker, text) pairs from this turn's story: speakers and NPCs the narrator names join the cast."""
    # ponytail: a name in the prose counts as on stage, so "nobody has seen Hara in weeks" adds him; a judge call
    # could tell talk-about from presence if that shows up in soaks.
    for speaker, text in lines:
        for name in _named(text if speaker == "narrator" else speaker):
            if name not in session.present:
                session.present.append(name)


def present_line(session: Session) -> str:
    who = ", ".join(session.present) or "no named characters"
    return f"Present: {who}. Anyone else must arrive on screen first."
