from dataclasses import dataclass

from ruleset.attributes import Attribute, modifier


@dataclass(frozen=True)
class Skill:
    name: str
    governing_attribute: Attribute
    description: str


STARTING_SKILL_POINTS = 8


SKILLS: dict[str, Skill] = {
    "melee": Skill(
        name="Melee",
        governing_attribute=Attribute.BODY,
        description="Close-quarters combat with blades, fists, or improvised weapons.",
    ),
    "athletics": Skill(
        name="Athletics",
        governing_attribute=Attribute.BODY,
        description="Running, climbing, jumping, and other raw physical feats.",
    ),
    "ranged_combat": Skill(
        name="Ranged Combat",
        governing_attribute=Attribute.REFLEXES,
        description="Firearms and thrown weapons at range.",
    ),
    "stealth": Skill(
        name="Stealth",
        governing_attribute=Attribute.REFLEXES,
        description="Moving unseen, staying quiet, avoiding detection.",
    ),
    "piloting": Skill(
        name="Piloting",
        governing_attribute=Attribute.REFLEXES,
        description="Driving or flying vehicles, high-speed maneuvers.",
    ),
    "hacking": Skill(
        name="Hacking",
        governing_attribute=Attribute.TECH,
        description="Breaching networks, bypassing security software, digital intrusion.",
    ),
    "engineering": Skill(
        name="Engineering",
        governing_attribute=Attribute.TECH,
        description="Building, repairing, and modifying gear and cyberware.",
    ),
    "demolitions": Skill(
        name="Demolitions",
        governing_attribute=Attribute.TECH,
        description="Explosives - rigging, defusing, controlled destruction.",
    ),
    "intimidation": Skill(
        name="Intimidation",
        governing_attribute=Attribute.COOL,
        description="Coercion through threat, presence, or reputation.",
    ),
    "streetwise": Skill(
        name="Streetwise",
        governing_attribute=Attribute.COOL,
        description="Reading the street - contacts, black markets, gang politics.",
    ),
    "perception": Skill(
        name="Perception",
        governing_attribute=Attribute.INTELLECT,
        description="Noticing details, spotting danger, reading a scene.",
    ),
    "deduction": Skill(
        name="Deduction",
        governing_attribute=Attribute.INTELLECT,
        description="Piecing together clues, drawing logical conclusions.",
    ),
    "persuasion": Skill(
        name="Persuasion",
        governing_attribute=Attribute.PRESENCE,
        description="Convincing others through charm, logic, or negotiation.",
    ),
    "performance": Skill(
        name="Performance",
        governing_attribute=Attribute.PRESENCE,
        description="Holding a crowd - music, acting, showmanship.",
    ),
}


def skill_cap(attribute_score: int) -> int:
    return min(5, modifier(attribute_score) + 3)


# Which attributes a roll may pair with each skill. The skill spec (2026-08-24) follows Cyberpunk 2077 2.0's loose
# binding, so a skill isn't locked to its governing attribute - but live play showed nonsense pairs (Stealth with
# Presence). These are the governing attribute plus the plausible alternatives, the extra ones from Cyberpunk RED's
# own pairings (Melee, Athletics and Stealth off DEX = Reflexes) or the spec's example (Perception vs Reflexes).
ROLL_ATTRIBUTES: dict[str, tuple[Attribute, ...]] = {
    "melee": (Attribute.BODY, Attribute.REFLEXES),
    "athletics": (Attribute.BODY, Attribute.REFLEXES),
    "ranged_combat": (Attribute.REFLEXES,),
    "stealth": (Attribute.REFLEXES, Attribute.COOL),
    "piloting": (Attribute.REFLEXES,),
    "hacking": (Attribute.TECH, Attribute.INTELLECT),
    "engineering": (Attribute.TECH, Attribute.INTELLECT),
    "demolitions": (Attribute.TECH,),
    "intimidation": (Attribute.COOL, Attribute.BODY, Attribute.PRESENCE),
    "streetwise": (Attribute.COOL, Attribute.PRESENCE),
    "perception": (Attribute.INTELLECT, Attribute.REFLEXES),
    "deduction": (Attribute.INTELLECT,),
    "persuasion": (Attribute.PRESENCE, Attribute.COOL),
    "performance": (Attribute.PRESENCE, Attribute.COOL),
}


def roll_attribute(skill: str, asked: str) -> Attribute:
    """The narrator's attribute if it's a sensible pair for the skill, else the skill's governing attribute."""
    allowed = ROLL_ATTRIBUTES.get(skill, (SKILLS[skill].governing_attribute,))
    return next((a for a in allowed if a.value == asked), SKILLS[skill].governing_attribute)
