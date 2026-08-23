from dataclasses import asdict

from engine.session import Session
from engine.turns import current_turn, is_players_turn

_REDACTED_FIELDS = ("name", "role", "health", "max_health", "armor", "conditions")


def build_view(session: Session, viewer_id: str) -> dict:
    characters = {}
    for player_id, character in session.characters.items():
        if player_id == viewer_id:
            characters[player_id] = asdict(character)
        else:
            full = asdict(character)
            characters[player_id] = {field: full[field] for field in _REDACTED_FIELDS}

    return {
        "session_id": session.session_id,
        "in_combat": session.in_combat,
        "current_turn": current_turn(session),
        "is_your_turn": is_players_turn(session, viewer_id),
        "log": session.log,
        "location": session.location,
        "scene_mood": session.scene_mood,
        "active_objectives": session.active_objectives,
        "characters": characters,
    }
