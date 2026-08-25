from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, end_combat, join, roll_initiative
from ruleset.attributes import Attribute
from ruleset.roles import ROLES
from ruleset.skills import SKILLS, STARTING_SKILL_POINTS, skill_cap

ATTRIBUTE_BASE_SCORE = 10
ATTRIBUTE_BUDGET = 12
ATTRIBUTE_MIN = 6
ATTRIBUTE_MAX = 14


def _starting_attributes(role: str) -> dict[str, int]:
    starting = {attr.value: ATTRIBUTE_BASE_SCORE for attr in Attribute}
    if role in ROLES:
        starting[ROLES[role].primary_attribute.value] = ATTRIBUTE_BASE_SCORE + 1
    return starting


def _validate_and_finalize_attributes(character_data: dict) -> None:
    attributes = character_data.get("attributes") or {}
    if not isinstance(attributes, dict):
        raise ValueError(f"attributes must be a dict, got {type(attributes).__name__}")
    starting = _starting_attributes(character_data.get("role"))

    finalized = dict(starting)
    spent = 0
    for name, score in attributes.items():
        if name not in starting:
            raise ValueError(f"unknown attribute: {name!r}")
        if not isinstance(score, int) or isinstance(score, bool):
            raise ValueError(f"attribute {name!r} score {score!r} must be an int")
        if score < ATTRIBUTE_MIN or score > ATTRIBUTE_MAX:
            raise ValueError(
                f"attribute {name!r} score {score} must be between {ATTRIBUTE_MIN} and {ATTRIBUTE_MAX}"
            )
        finalized[name] = score
        spent += score - starting[name]

    if spent > ATTRIBUTE_BUDGET:
        raise ValueError(f"attribute points spent ({spent}) exceed the budget ({ATTRIBUTE_BUDGET})")

    character_data["attributes"] = finalized


def _skill_rank_cap(skill_name: str, attributes: dict[str, int]) -> int:
    governing = SKILLS[skill_name].governing_attribute.value
    return skill_cap(attributes.get(governing, 10))


def _validate_and_finalize_skills(character_data: dict) -> None:
    skills = character_data.get("skills") or {}
    if not isinstance(skills, dict):
        raise ValueError(f"skills must be a dict, got {type(skills).__name__}")
    attributes = character_data.get("attributes") or {}
    # Type-check every rank before summing - sum() itself throws an
    # unhandled TypeError on a string/list rank, which would bypass this
    # function's ValueError-at-the-boundary convention entirely.
    for skill_name, rank in skills.items():
        if skill_name not in SKILLS:
            raise ValueError(f"unknown skill: {skill_name!r}")
        # bool is a subclass of int (isinstance(True, int) is True) - excluded
        # explicitly so True/False can't slip through as 1/0.
        if not isinstance(rank, int) or isinstance(rank, bool):
            raise ValueError(f"skill {skill_name!r} rank {rank!r} must be an int")
    spent = sum(skills.values())
    if spent > STARTING_SKILL_POINTS:
        raise ValueError(
            f"skill points spent ({spent}) exceed the starting budget ({STARTING_SKILL_POINTS})"
        )
    for skill_name, rank in skills.items():
        if rank < 0:
            raise ValueError(f"skill {skill_name!r} rank {rank} cannot be negative")
        cap = _skill_rank_cap(skill_name, attributes)
        if rank > cap:
            raise ValueError(f"skill {skill_name!r} rank {rank} exceeds cap {cap}")
    # Never trust the client to report its own leftover budget - the server
    # is the one place total spent is actually verified, so it's also the
    # only place that gets to decide what's left over.
    character_data["unspent_skill_points"] = STARTING_SKILL_POINTS - spent
    # Drop dead 0-rank entries (e.g. a pre-join +/- that nets back to 0) so
    # they don't persist forever - CharacterSheetOverlay's "None trained."
    # fallback checks len(character.skills) == 0 and would never see it again.
    character_data["skills"] = {name: rank for name, rank in skills.items() if rank > 0}


def handle_message(session: Session, message: dict, player_id: str) -> None:
    message_type = message.get("type")
    if message_type is None:
        raise ValueError("missing 'type' in message")

    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        _validate_and_finalize_attributes(character_data)
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

    elif message_type == "allocate_attribute_points":
        if player_id not in session.characters:
            raise ValueError(f"unknown player_id: {player_id!r}")
        attribute_name = message.get("attribute")
        amount = message.get("amount")
        if attribute_name not in {attr.value for attr in Attribute}:
            raise ValueError(f"unknown attribute: {attribute_name!r}")
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError(f"invalid amount: {amount!r}")
        character = session.characters[player_id]
        if character.unspent_attribute_points < amount:
            raise ValueError(
                f"insufficient attribute points: has {character.unspent_attribute_points}, needs {amount}"
            )
        new_score = character.attributes.get(attribute_name, ATTRIBUTE_BASE_SCORE) + amount
        if new_score > ATTRIBUTE_MAX:
            raise ValueError(
                f"attribute {attribute_name!r} score {new_score} would exceed the maximum {ATTRIBUTE_MAX}"
            )
        character.attributes[attribute_name] = new_score
        character.unspent_attribute_points -= amount

    elif message_type == "advance_turn":
        advance_turn(session)

    elif message_type == "end_combat":
        end_combat(session)

    else:
        raise ValueError(f"unknown message type: {message_type!r}")
