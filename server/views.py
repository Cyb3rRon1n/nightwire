from dataclasses import asdict

from engine.chrome import usable_overclocks
from engine.session import Session
from engine.turns import current_turn, is_players_turn
from narrator.place_art import location_art

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
        "type": "state",
        "session_id": session.session_id,
        "in_combat": session.in_combat,
        "current_turn": current_turn(session),
        "is_your_turn": is_players_turn(session, viewer_id),
        "log": session.log[-50:],
        "location": session.location,
        # Approved art for the current place, shown behind the conversation until a scene image arrives.
        "location_art": location_art(session.location),
        "scene_mood": session.scene_mood,
        "active_objectives": session.active_objectives,
        "pending_chrome_offers": (
            {viewer_id: session.pending_chrome_offers[viewer_id]} if viewer_id in session.pending_chrome_offers else {}
        ),
        "pending_rolls": {
            pid: {**pending, "overclocks": usable_overclocks(session.characters[pid], pending["skill"])
                  if pid == viewer_id and pid in session.characters and "skill" in pending else []}
            for pid, pending in session.pending_rolls.items()
        },
        "characters": characters,
    }
