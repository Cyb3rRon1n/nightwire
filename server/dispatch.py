from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, end_combat, join, roll_initiative
from ruleset.skills import SKILLS, STARTING_SKILL_POINTS, skill_cap


def _skill_rank_cap(skill_name: str, attributes: dict[str, int]) -> int:
    governing = SKILLS[skill_name].governing_attribute.value
    return skill_cap(attributes.get(governing, 10))


def _validate_and_finalize_skills(character_data: dict) -> None:
    skills = character_data.get("skills") or {}
    attributes = character_data.get("attributes") or {}
    spent = sum(skills.values())
    if spent > STARTING_SKILL_POINTS:
        raise ValueError(
            f"skill points spent ({spent}) exceed the starting budget ({STARTING_SKILL_POINTS})"
        )
    for skill_name, rank in skills.items():
        if skill_name not in SKILLS:
            raise ValueError(f"unknown skill: {skill_name!r}")
        if rank < 0:
            raise ValueError(f"skill {skill_name!r} rank {rank} cannot be negative")
        cap = _skill_rank_cap(skill_name, attributes)
        if rank > cap:
            raise ValueError(f"skill {skill_name!r} rank {rank} exceeds cap {cap}")
    # Never trust the client to report its own leftover budget - the server
    # is the one place total spent is actually verified, so it's also the
    # only place that gets to decide what's left over.
    character_data["unspent_skill_points"] = STARTING_SKILL_POINTS - spent


def handle_message(session: Session, message: dict, player_id: str) -> None:
    message_type = message.get("type")
    if message_type is None:
        raise ValueError("missing 'type' in message")

    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        _validate_and_finalize_skills(character_data)
        join(session, CharacterSheet(**character_data))

    elif message_type == "roll_initiative":
        if player_id not in session.characters:
            raise ValueError(f"unknown player_id: {player_id!r}")
        total = roll_initiative(session, player_id)
        if total is not None:
            session.log.append(f"[initiative: {session.characters[player_id].name} rolled {total}]")

    elif message_type == "allocate_skill_points":
        if player_id not in session.characters:
            raise ValueError(f"unknown player_id: {player_id!r}")
        skill_name = message.get("skill")
        amount = message.get("amount")
        if skill_name not in SKILLS:
            raise ValueError(f"unknown skill: {skill_name!r}")
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError(f"invalid amount: {amount!r}")
        character = session.characters[player_id]
        if character.unspent_skill_points < amount:
            raise ValueError(
                f"insufficient skill points: has {character.unspent_skill_points}, needs {amount}"
            )
        cap = _skill_rank_cap(skill_name, character.attributes)
        new_rank = character.skills.get(skill_name, 0) + amount
        if new_rank > cap:
            raise ValueError(f"skill {skill_name!r} rank {new_rank} would exceed cap {cap}")
        character.skills[skill_name] = new_rank
        character.unspent_skill_points -= amount

    elif message_type == "advance_turn":
        advance_turn(session)

    elif message_type == "end_combat":
        end_combat(session)

    else:
        raise ValueError(f"unknown message type: {message_type!r}")
