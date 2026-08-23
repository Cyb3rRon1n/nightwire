from engine.character import CharacterSheet
from engine.session import Session


def join(session: Session, character: CharacterSheet) -> None:
    session.characters.setdefault(character.player_id, character)
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


def start_combat(session: Session, initiative_rolls: dict[str, int]) -> None:
    if session.in_combat:
        return
    session.pre_combat_turn_order = list(session.turn_order)
    session.turn_order = sorted(initiative_rolls, key=lambda pid: -initiative_rolls[pid])
    session.current_turn_index = 0
    session.in_combat = True


def end_combat(session: Session) -> None:
    if not session.in_combat:
        return
    pre_combat = session.pre_combat_turn_order or []
    latecomers = [pid for pid in session.turn_order if pid not in pre_combat]
    session.turn_order = pre_combat + latecomers
    session.pre_combat_turn_order = None
    session.current_turn_index = 0
    session.in_combat = False


def advance_turn(session: Session) -> None:
    if session.in_combat and session.turn_order:
        session.current_turn_index = (session.current_turn_index + 1) % len(session.turn_order)
