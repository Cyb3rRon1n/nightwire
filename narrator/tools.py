import random
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.session import Session
from ruleset.attributes import modifier
from ruleset.difficulty import Difficulty
from ruleset.resolution import resolve_roll


class RequestRoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    attribute: Literal["body", "reflexes", "tech", "cool", "intellect", "presence"]
    skill: Literal[
        "melee", "athletics", "ranged_combat", "stealth", "piloting",
        "hacking", "engineering", "demolitions", "intimidation", "streetwise",
        "perception", "deduction", "persuasion", "performance",
    ]
    difficulty: Literal["easy", "moderate", "hard", "extreme"]
    reason: str


class ApplyCharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    health_delta: int = 0
    armor_delta: int = 0
    add_conditions: list[str] = []
    remove_conditions: list[str] = []
    add_inventory: list[str] = []
    remove_inventory: list[str] = []
    skill_points_delta: int = 0
    attribute_points_delta: int = 0


class UpdateWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str | None = None
    scene_mood: str | None = None
    add_objectives: list[str] = []
    remove_objectives: list[str] = []


def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    character = session.characters[tool.player_id]
    raw_score = character.attributes.get(tool.attribute, 10)
    attribute_mod = modifier(raw_score)
    skill_mod = character.skills.get(tool.skill, 0)
    die_result = random.randint(1, 10)
    dc = Difficulty[tool.difficulty.upper()].value
    outcome = resolve_roll(die_result, attribute_mod, skill_mod, dc)
    return {
        "die_result": die_result,
        "attribute_mod": attribute_mod,
        "skill_mod": skill_mod,
        "dc": dc,
        "outcome": outcome.value,
    }


def _execute_apply_character_update(session: Session, tool: ApplyCharacterUpdate) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    character = session.characters[tool.player_id]

    character.health = max(0, min(character.max_health, character.health + tool.health_delta))
    character.armor = max(0, character.armor + tool.armor_delta)
    character.unspent_skill_points = max(0, character.unspent_skill_points + tool.skill_points_delta)
    character.unspent_attribute_points = max(0, character.unspent_attribute_points + tool.attribute_points_delta)

    for condition in tool.add_conditions:
        if condition not in character.conditions:
            character.conditions.append(condition)
    for condition in tool.remove_conditions:
        if condition in character.conditions:
            character.conditions.remove(condition)

    for item in tool.add_inventory:
        character.inventory.append(item)
    for item in tool.remove_inventory:
        if item in character.inventory:
            character.inventory.remove(item)

    return {
        "player_id": tool.player_id,
        "health": character.health,
        "armor": character.armor,
        "unspent_skill_points": character.unspent_skill_points,
        "unspent_attribute_points": character.unspent_attribute_points,
    }


def _execute_update_world(session: Session, tool: UpdateWorld) -> dict:
    if tool.location is not None:
        session.location = tool.location
    if tool.scene_mood is not None:
        session.scene_mood = tool.scene_mood
    for objective in tool.add_objectives:
        if objective not in session.active_objectives:
            session.active_objectives.append(objective)
    for objective in tool.remove_objectives:
        if objective in session.active_objectives:
            session.active_objectives.remove(objective)

    return {
        "location": session.location,
        "scene_mood": session.scene_mood,
        "active_objectives": list(session.active_objectives),
    }


# start_combat/end_combat are deliberately absent: real combat state only
# ever starts via a player-sent message (server/dispatch.py -> engine/turns.py,
# with real initiative rolls) - the narrator's own copy of these tools was a
# no-op stub that fired on nearly every turn regardless of instruction
# (a temperature-resistant model bias, not a fixable prompt-wording bug -
# see ROADMAP.md's Phase 3 entry). Removing it from the tool surface it can
# call closes the bug at the root instead of continuing to prompt-tune it.
TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Callable[[Session, BaseModel], dict]]] = {
    "request_roll": (RequestRoll, _execute_request_roll),
    "apply_character_update": (ApplyCharacterUpdate, _execute_apply_character_update),
    "update_world": (UpdateWorld, _execute_update_world),
}


def execute_tool(session: Session, tool_name: str, tool_args: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"unknown tool: {tool_name!r}")
    model_cls, executor = TOOL_REGISTRY[tool_name]
    tool = model_cls(**tool_args)
    return executor(session, tool)
