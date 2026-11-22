import re
from dataclasses import asdict
from pathlib import Path

from engine.chrome import usable_overclocks
from engine.phone import unread
from engine.session import Session
from engine.turns import current_turn, is_players_turn
from narrator import gossip, places
from narrator.cast import _player_turns
from narrator.place_art import location_art
from narrator.tools import roll_chance

CHARACTER_ART = Path(__file__).parent.parent / "narrator" / "worlds" / "character_art"
_REDACTED_FIELDS = ("name", "role", "health", "max_health", "armor", "conditions")


def _portrait(name: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"character-art/{slug}.jpg" if (CHARACTER_ART / f"{slug}.jpg").is_file() else None


def _phone_view(session: Session, viewer_id: str) -> dict:
    phone = session.phone.get(viewer_id)  # never create one just by looking
    if phone is None:
        return {"contacts": [], "threads": {}, "typing": []}
    counts = unread(session, viewer_id)
    threads = {name: sorted((m for m in msgs if m["text"] is not None and m["deliver_at"] <= phone["turn"]),
                            key=lambda m: m["deliver_at"])  # stable: ties keep posting order
               for name, msgs in phone["threads"].items()}
    return {
        "contacts": [{"name": c["name"], "role": c["role"], "trust": int(c["trust"]),
                      "unread": counts.get(c["name"], 0), "portrait": _portrait(c["name"])}
                     for c in phone["contacts"].values()],
        "threads": {name: [{"sender": m["sender"], "text": m["text"], "turn": m["turn"]} for m in msgs]
                    for name, msgs in threads.items()},
        "typing": [name for name, msgs in phone["threads"].items() if any(m["text"] is None for m in msgs)],
    }


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
        # The whole session's images: the gallery was built from the last 50 lines and lost older ones (playthrough).
        "images": [line[len("[image: "):-1] for line in session.log if line.startswith("[image: ") and line.endswith("]")],
        "location": session.location,
        # Approved art for the current place, shown behind the conversation until a scene image arrives.
        "location_art": location_art(session.location),
        "scene_mood": session.scene_mood,
        "active_objectives": session.active_objectives,
        "promises": [{"who": p["who"], "what": p["what"], "ago": _turns_ago(session, p["turn"])} for p in session.promises],
        "can_rate": session.last_turn is not None,
        "last_rating": session.last_rating,
        "checkin": session.checkin_open,
        "people": [{"name": n, "who": p["who"], "what": p["what"], "place": p.get("place") or p.get("district"),
                    "ago": _turns_ago(session, p["turn"])} for n, p in reversed(session.people.items())],
        "here": places.view(session),
        "street": gossip.street(session),
        "journal": [{**j, "ago": _turns_ago(session, j["turn"])} for j in reversed(session.journal)],
        "pending_chrome_offers": (
            {viewer_id: session.pending_chrome_offers[viewer_id]} if viewer_id in session.pending_chrome_offers else {}
        ),
        "pending_rolls": {
            pid: {**pending, "overclocks": usable_overclocks(session.characters[pid], pending["skill"])
                  if pid == viewer_id and pid in session.characters and "skill" in pending else []}
            for pid, pending in session.pending_rolls.items()
        },
        "characters": characters,
        "phone": _phone_view(session, viewer_id),
        "suggestions": _suggestions_view(session, viewer_id),
    }


def _suggestions_view(session: Session, viewer_id: str) -> list[dict]:
    character = session.characters.get(viewer_id)
    if character is None:
        return []
    return [{**{k: chip.get(k) for k in ("id", "text", "skill", "attribute", "difficulty")},
             # computed here so it always matches the current sheet
             "chance": roll_chance(character, chip["attribute"], chip["skill"], chip["difficulty"]) if chip.get("skill") else None}
            for chip in session.suggestions.get(viewer_id, [])]


def _turns_ago(session: Session, turn: int) -> int:
    return max(0, _player_turns(session) - turn)
