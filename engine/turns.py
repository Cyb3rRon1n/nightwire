import random

from engine.character import CharacterSheet
from engine.session import Session
from ruleset.attributes import modifier


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


def roll_initiative(session: Session, player_id: str) -> int | None:
    # Each connected client can only ever roll for its own player_id (see
    # server/app.py) - the server, not the client, computes the real
    # 1d10 + Reflexes total, since a client's own view of teammates'
    # attributes is redacted (server/views.py) and can't be trusted to
    # compute it honestly for anyone but itself.
    if session.in_combat or player_id in session.pending_initiative:
        return None

    raw_score = session.characters[player_id].attributes.get("reflexes", 10)
    total = random.randint(1, 10) + modifier(raw_score)
    session.pending_initiative[player_id] = total

    if set(session.pending_initiative) == set(session.characters):
        start_combat(session, session.pending_initiative)
        session.pending_initiative = {}

    return total


def end_combat(session: Session) -> None:
    session.pending_initiative = {}
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
