from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, end_combat, join, start_combat


def handle_message(session: Session, message: dict) -> None:
    message_type = message.get("type")
    if message_type is None:
        raise ValueError("missing 'type' in message")

    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        join(session, CharacterSheet(**character_data))

    elif message_type == "start_combat":
        initiative_rolls = message.get("initiative_rolls")
        if initiative_rolls is None:
            raise ValueError("missing 'initiative_rolls' in start_combat message")
        unknown = set(initiative_rolls) - set(session.characters)
        if unknown:
            raise ValueError(f"initiative_rolls for players not in session: {sorted(unknown)}")
        start_combat(session, initiative_rolls)

    elif message_type == "advance_turn":
        advance_turn(session)

    elif message_type == "end_combat":
        end_combat(session)

    else:
        raise ValueError(f"unknown message type: {message_type!r}")
