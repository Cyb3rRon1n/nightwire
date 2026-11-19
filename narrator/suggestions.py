"""Suggested actions (spec 2026-11-18-suggested-actions-design.md): up to 3 chips after each story turn, one plain,
the others tagged with the roll they would cause. The model writes them; the engine checks every tag."""

import uuid
from typing import get_args

from narrator.movement import places_in
from narrator.tools import RequestRoll
from narrator.world import _mentions, _normalize, kuroshio
from ruleset.attributes import Attribute
from ruleset.difficulty import STAKES, difficulty_for
from ruleset.skills import SKILLS, roll_attribute

LOOK_AROUND = "I look around."
_SKILL_NAMES = get_args(RequestRoll.model_fields["skill"].annotation)
_ATTRIBUTES = get_args(RequestRoll.model_fields["attribute"].annotation)
_MAX_WORDS = 20  # the prompt asks for 12; this only drops runaways

SCHEMA = {
    "type": "object",
    "properties": {"chips": {"type": "array", "maxItems": 3, "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "skill": {"type": "string", "enum": ["none", *_SKILL_NAMES]},
            "attribute": {"type": "string", "enum": ["none", *_ATTRIBUTES]},
            "stakes": {"type": "string", "enum": ["none", *STAKES]},
        },
        "required": ["text", "skill", "attribute", "stakes"],
    }}},
    "required": ["chips"],
}

_SYSTEM = "You suggest what a player could do next in a cyberpunk tabletop game. Answer only from the scene."


async def suggest(client, story: list[str], place: str | None, character) -> list:
    best = sorted(character.skills, key=character.skills.get, reverse=True)[:3]
    told = _normalize("\n".join(story))
    present = [npc.name for npc in kuroshio().npcs if _mentions(npc, told)]
    prompt = (
        "Scene (latest last):\n" + "\n".join(story) + "\n\n"
        f"Place: {place or 'unknown'}. People here: {', '.join(present) or 'nobody named'}. "
        f"Player character: {character.name}, a {character.role}; best skills: {', '.join(best) or 'none'}.\n\n"
        "Suggest 3 moves this character could make now:\n"
        '- one plain move that needs no roll (talk, look, leave): skill, attribute and stakes "none";\n'
        "- two risky moves with different approaches (social, tech, stealth, force) that test two different "
        "skills, each with the skill and attribute it tests and its stakes; use the character's best skills where "
        "the scene allows.\n"
        'Each move: first person, like "I ask her about the ledger", at most 12 words, only the people listed and '
        "things the scene describes, and never say how it turns out."
    )
    answer = await client.judge([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}], SCHEMA)
    return answer.get("chips")


def _plain(text: str) -> dict:
    return {"text": text, "skill": None, "attribute": None, "stakes": None, "difficulty": None}


def _invents(text: str, scene: str) -> bool:
    """Names a known place or person the scene never showed (chips soak 2026-11-18: "the clinic's back alley" from
    inside the izakaya). The prompt rule alone didn't hold, so the engine checks, as the referee does for leads."""
    if places_in(text) - places_in(scene):
        return True
    t, s = _normalize(text), _normalize(scene)
    return any(_mentions(npc, t) and not _mentions(npc, s) for npc in kuroshio().npcs)


def check_chips(raw, character, recent_stakes: list[str], scene: str = "") -> list[dict]:
    if not isinstance(raw, list):
        return []
    plain, tagged = [], []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text or len(text.split()) > _MAX_WORDS or (scene and _invents(text, scene)):
            continue
        skill, stakes = item.get("skill"), item.get("stakes")
        if skill not in SKILLS or stakes not in STAKES:
            plain.append(_plain(text))
            continue
        if character.bodiless and SKILLS[skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
            continue  # no body to climb, fight or dodge with: no physical chips for a bodiless character
        if any(t["skill"] == skill for t in tagged):
            continue  # two risky chips, two different skills (chips soak 2026-11-18: hacking and stealth every turn)
        # Chips are fair bets the player picks (chips soak 2026-11-18: 4 of 9 were Extreme): no Extreme, one Hard.
        stakes = "high" if stakes == "extreme" else stakes
        if stakes == "high" and any(t["stakes"] == "high" for t in tagged):
            stakes = "normal"
        attribute = roll_attribute(skill, str(item.get("attribute"))).value
        effective, difficulty = difficulty_for(stakes, recent_stakes)
        level = difficulty.name.lower()
        tagged.append({"text": text, "skill": skill, "attribute": attribute, "stakes": effective,
                       "difficulty": level})
    if not plain and not tagged:
        return []
    chips = [plain[0] if plain else _plain(LOOK_AROUND), *tagged[:2]]
    chips += plain[1:1 + 3 - len(chips)]
    for chip in chips:
        chip["id"] = uuid.uuid4().hex[:8]
    return chips
