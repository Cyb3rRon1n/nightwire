from ruleset.cyberware import (
    CHROME, SOCIAL_SKILLS, chrome_roll_bonus, humanity_tier, overclock_tier_bonus, slot_capacity, social_penalty,
)
from ruleset.skills import SKILLS


def test_catalog_has_the_eleven_spec_items():
    assert list(CHROME) == [
        "hawkeye_optics", "reflex_wires", "kagerou", "kama_blades", "oni_arms", "lacquer_skin",
        "yomi_jack", "pain_editor", "silk_tongue", "kumo_hand", "neon_ink",
    ]
    assert (CHROME["kagerou"].humanity_cost, CHROME["kagerou"].installments) == (10, 5)
    assert CHROME["neon_ink"].humanity_cost == 0


def test_catalog_skills_are_real_and_costs_non_negative():
    for chrome in CHROME.values():
        assert all(skill in SKILLS for skill in chrome.roll_bonus)
        assert chrome.humanity_cost >= 0 and chrome.installments >= 1


def test_overclocks():
    assert CHROME["kagerou"].overclock.second_die and CHROME["kagerou"].overclock.bonus == 2
    assert CHROME["kagerou"].overclock.skill is None
    assert CHROME["yomi_jack"].overclock.skill == "hacking" and CHROME["yomi_jack"].overclock.bonus == 3
    assert [c.id for c in CHROME.values() if c.overclock] == ["kagerou", "yomi_jack"]


def test_slot_capacity():
    assert slot_capacity({"body": 6}) == 2  # 3 + (-2) = 1 -> minimum 2
    assert slot_capacity({"body": 10}) == 3
    assert slot_capacity({"body": 16}) == 6


def test_tiers_and_penalties():
    assert [humanity_tier(h) for h in (100, 70, 69, 40, 39, 20, 19, 1, 0)] == [
        "Steady", "Steady", "Frayed", "Frayed", "Slipping", "Slipping", "Edge", "Edge", "Gone too far",
    ]
    assert [social_penalty(h) for h in (70, 40, 39, 19, 0)] == [0, 0, -1, -2, -2]
    assert [overclock_tier_bonus(h) for h in (40, 39, 1)] == [0, 1, 1]
    assert SOCIAL_SKILLS == ("persuasion", "performance")


def test_chrome_roll_bonus_sums_installed_items():
    assert chrome_roll_bonus(["kama_blades", "oni_arms"], "melee") == 3
    assert chrome_roll_bonus(["kama_blades"], "stealth") == 0


def test_selfhood_tiers_mirror_humanity_thresholds():
    from ruleset.cyberware import selfhood_tier
    assert [selfhood_tier(v) for v in (0, 19, 20, 39, 40, 59, 60, 79, 80, 100)] == [
        "Appliance", "Appliance", "Flickering", "Flickering", "Waking", "Waking",
        "Someone", "Someone", "Awake", "Awake",
    ]
