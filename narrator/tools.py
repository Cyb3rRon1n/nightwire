import random
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.debt import active_chrome
from engine.session import Session
from ruleset.attributes import modifier
from ruleset.cyberware import CHROME, SOCIAL_SKILLS, chrome_roll_bonus, overclock_tier_bonus, slot_capacity, social_penalty
from ruleset.difficulty import STAKES, Difficulty
from ruleset.resolution import resolve_roll

# Write-time sanity caps, not the primary context-budget mechanism (that's
# server/narration.py's _select_npc_memory_for_context, a separate,
# num_ctx-adaptive read-time bound) - these just stop truly unbounded
# growth over a very long campaign. Deliberately generous.
_MAX_NPCS = 50
_MAX_FACTS_PER_NPC = 5


class RequestRoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    attribute: Literal["body", "reflexes", "tech", "cool", "intellect", "presence"]
    skill: Literal[
        "melee", "athletics", "ranged_combat", "stealth", "piloting",
        "hacking", "engineering", "demolitions", "intimidation", "streetwise",
        "perception", "deduction", "persuasion", "performance",
    ]
    stakes: Literal["low", "normal", "high", "extreme"]
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
    # Milestone grants from an 8B model - bounded at the schema so one
    # hallucinated large value can't permanently max a character in a
    # single turn. A whole campaign hands out only a handful of points.
    skill_points_delta: int = Field(0, ge=0, le=3)
    attribute_points_delta: int = Field(0, ge=0, le=1)


ChromeId = Literal[
    "hawkeye_optics", "reflex_wires", "kagerou", "kama_blades", "oni_arms", "lacquer_skin",
    "yomi_jack", "pain_editor", "silk_tongue", "kumo_hand", "neon_ink",
]


class OfferChrome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    item: ChromeId


class UpdateWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str | None = None
    scene_mood: str | None = None
    add_objectives: list[str] = []
    remove_objectives: list[str] = []


class RememberNPC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Schema-bounded so one verbose value from an 8B model can't consume a
    # large fraction of the already-small NPC memory context budget on its
    # own - same precedent ApplyCharacterUpdate's skill_points_delta/
    # attribute_points_delta already establishes in this file.
    name: str = Field(..., max_length=100)
    fact: str = Field(..., max_length=200)


def roll_check(character, attribute: str, skill: str, difficulty: str, overclock_id: str | None = None) -> dict:
    attribute_mod = modifier(character.attributes.get(attribute, 10))
    skill_mod = character.skills.get(skill, 0) + chrome_roll_bonus(active_chrome(character), skill)
    if skill in SOCIAL_SKILLS:
        skill_mod += social_penalty(character.humanity)
    dc = Difficulty[difficulty.upper()].value
    die = random.randint(1, 10)
    result = {"attribute_mod": attribute_mod, "skill_mod": skill_mod, "dc": dc}
    bonus = 0
    if overclock_id is not None:
        oc = CHROME[overclock_id].overclock
        bonus = oc.bonus + overclock_tier_bonus(character.humanity)
        result.update(overclock=overclock_id, overclock_bonus=bonus)
        if oc.second_die:
            second = random.randint(1, 10)
            result.update(first_die=die, second_die=second)
            die = max(die, second)
    result["die_result"] = die
    result["outcome"] = resolve_roll(die, attribute_mod, skill_mod + bonus, dc).value
    return result


def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    difficulty = STAKES[tool.stakes].name.lower()
    return roll_check(session.characters[tool.player_id], tool.attribute, tool.skill, difficulty)


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


def _execute_remember_npc(session: Session, tool: RememberNPC) -> dict:
    # .pop then re-insert moves this NPC to the end of the dict - Python's
    # insertion-ordering gives LRU-by-touch for free, no extra state needed.
    facts = session.npc_memory.pop(tool.name, [])
    facts.append(tool.fact)
    facts = facts[-_MAX_FACTS_PER_NPC:]
    session.npc_memory[tool.name] = facts
    if len(session.npc_memory) > _MAX_NPCS:
        oldest = next(iter(session.npc_memory))
        del session.npc_memory[oldest]
    return {"name": tool.name, "facts": list(facts)}


def _execute_offer_chrome(session: Session, tool: OfferChrome) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    character = session.characters[tool.player_id]
    if tool.item in character.chrome:
        raise ValueError(f"{tool.item!r} is already installed")
    if len(character.chrome) >= slot_capacity(character.attributes):
        raise ValueError("no free chrome slot")
    session.pending_chrome_offers[tool.player_id] = tool.item
    return {"offered": tool.item}


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
    "remember_npc": (RememberNPC, _execute_remember_npc),
    "offer_chrome": (OfferChrome, _execute_offer_chrome),
}


def execute_tool(session: Session, tool_name: str, tool_args: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"unknown tool: {tool_name!r}")
    model_cls, executor = TOOL_REGISTRY[tool_name]
    tool = model_cls(**tool_args)
    return executor(session, tool)
