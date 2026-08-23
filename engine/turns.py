from engine.character import CharacterSheet
from engine.session import Session


def join(session: Session, character: CharacterSheet) -> None:
    session.characters[character.player_id] = character
    if character.player_id not in session.turn_order:
        session.turn_order.append(character.player_id)


def current_turn(session: Session) -> str | None:
    if not session.in_combat or not session.turn_order:
        return None
    return session.turn_order[session.current_turn_index % len(session.turn_order)]


def is_players_turn(session: Session, player_id: str) -> bool:
    if not session.in_combat:
        return True
    return current_turn(session) == player_id
