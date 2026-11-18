"""Suggested actions (spec 2026-11-18-suggested-actions-design.md): up to 3 chips after each story turn, one plain,
the others tagged with the roll they would cause. The model writes them; the engine checks every tag."""

import uuid
from typing import get_args

from narrator.tools import RequestRoll
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
    prompt = (
        "Scene (latest last):\n" + "\n".join(story) + "\n\n"
        f"Place: {place or 'unknown'}. Player character: {character.name}, a {character.role}; "
        f"best skills: {', '.join(best) or 'none'}.\n\n"
        "Suggest 3 moves this character could make now:\n"
        '- one plain move that needs no roll (talk, look, leave): skill, attribute and stakes "none";\n'
        "- two risky moves with different approaches (social, tech, stealth, force), each with the skill and "
        "attribute it tests and its stakes; use the character's best skills where the scene allows.\n"
        'Each move: first person, like "I talk the doorman down", at most 12 words, only people and things the '
        "scene has shown, and never say how it turns out."
    )
    answer = await client.judge([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}], SCHEMA)
    return answer.get("chips")


def _plain(text: str) -> dict:
    return {"text": text, "skill": None, "attribute": None, "stakes": None, "difficulty": None}


def check_chips(raw, character, recent_stakes: list[str]) -> list[dict]:
    if not isinstance(raw, list):
        return []
    plain, tagged = [], []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text or len(text.split()) > _MAX_WORDS:
            continue
        skill, stakes = item.get("skill"), item.get("stakes")
        if skill not in SKILLS or stakes not in STAKES:
            plain.append(_plain(text))
            continue
        if character.bodiless and SKILLS[skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
            continue  # no body to climb, fight or dodge with: no physical chips for a bodiless character
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
