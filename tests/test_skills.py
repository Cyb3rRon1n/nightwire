from ruleset.attributes import Attribute
from ruleset.skills import SKILLS, STARTING_SKILL_POINTS, Skill, skill_cap


def test_fourteen_skills_exist():
    assert len(SKILLS) == 14


def test_each_skill_has_a_valid_governing_attribute():
    for skill in SKILLS.values():
        assert isinstance(skill, Skill)
        assert isinstance(skill.governing_attribute, Attribute)


def test_every_skill_has_a_nonempty_description():
    for skill in SKILLS.values():
        assert skill.description.strip() != ""


def test_skills_grouped_by_governing_attribute():
    by_attribute: dict[Attribute, set[str]] = {}
    for internal_name, skill in SKILLS.items():
        by_attribute.setdefault(skill.governing_attribute, set()).add(internal_name)

    assert by_attribute[Attribute.BODY] == {"melee", "athletics"}
    assert by_attribute[Attribute.REFLEXES] == {"ranged_combat", "stealth", "piloting"}
    assert by_attribute[Attribute.TECH] == {"hacking", "engineering", "demolitions"}
    assert by_attribute[Attribute.COOL] == {"intimidation", "streetwise"}
    assert by_attribute[Attribute.INTELLECT] == {"perception", "deduction"}
    assert by_attribute[Attribute.PRESENCE] == {"persuasion", "performance"}


def test_skill_cap_scales_with_attribute_modifier():
    assert skill_cap(10) == 3  # modifier(10) == 0 -> 0 + 3
    assert skill_cap(16) == 5  # modifier(16) == 3 -> 3 + 3, clamped to 5
    assert skill_cap(8) == 2   # modifier(8) == -1 -> -1 + 3


def test_skill_cap_never_exceeds_five():
    assert skill_cap(30) == 5


def test_starting_skill_points_is_eight():
    assert STARTING_SKILL_POINTS == 8
