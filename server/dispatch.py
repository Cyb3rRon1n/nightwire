from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, end_combat, join, roll_initiative


def handle_message(session: Session, message: dict, player_id: str) -> None:
    message_type = message.get("type")
    if message_type is None:
        raise ValueError("missing 'type' in message")

    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        join(session, CharacterSheet(**character_data))

    elif message_type == "roll_initiative":
        if player_id not in session.characters:
            raise ValueError(f"unknown player_id: {player_id!r}")
        total = roll_initiative(session, player_id)
        if total is not None:
            session.log.append(f"[initiative: {session.characters[player_id].name} rolled {total}]")

    elif message_type == "advance_turn":
        advance_turn(session)

    elif message_type == "end_combat":
        end_combat(session)

    else:
        raise ValueError(f"unknown message type: {message_type!r}")
