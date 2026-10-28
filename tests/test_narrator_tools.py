from typing import get_args

import pytest

from engine.character import CharacterSheet
from engine.session import Session
from narrator.tools import RequestRoll, execute_tool
from ruleset.skills import SKILLS


def _session_with_character(**overrides) -> Session:
    session = Session(session_id="s1")
    defaults = dict(
        player_id="p1", name="Rook", role="solo", lifepath="streetkid",
        health=7, max_health=10, armor=2,
        conditions=["bleeding"], inventory=["stim pack"],
    )
    defaults.update(overrides)
    session.characters["p1"] = CharacterSheet(**defaults)
    return session


def test_request_roll_uses_the_characters_real_attribute_score():
    session = _session_with_character(attributes={"reflexes": 16})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill": "stealth", "difficulty": "easy", "reason": "dodge",
    })
    assert result["attribute_mod"] == 3  # modifier(16) == (16 - 10) // 2 == 3


def test_request_roll_looks_up_the_characters_real_skill_rank():
    session = _session_with_character(skills={"ranged_combat": 3})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill": "ranged_combat",
        "difficulty": "easy", "reason": "quickdraw",
    })
    assert result["skill_mod"] == 3


def test_request_roll_defaults_an_untrained_skill_to_zero():
    session = _session_with_character()
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "body", "skill": "melee",
        "difficulty": "easy", "reason": "x",
    })
    assert result["skill_mod"] == 0


def test_request_roll_rejects_an_unknown_player_id():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        execute_tool(session, "request_roll", {
            "player_id": "ghost", "attribute": "body", "skill": "melee", "difficulty": "easy", "reason": "x",
        })


def test_request_roll_rolls_a_real_die_and_resolves_the_outcome():
    session = _session_with_character(attributes={"reflexes": 14}, skills={"stealth": 2})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill": "stealth", "difficulty": "easy", "reason": "climbing a wall",
    })
    assert 1 <= result["die_result"] <= 10
    assert result["dc"] == 6
    assert result["outcome"] in ("clean_success", "complication", "failure")


def test_request_roll_rejects_an_unknown_difficulty():
    session = _session_with_character()
    with pytest.raises(ValueError):
        execute_tool(session, "request_roll", {
            "player_id": "p1", "attribute": "body", "skill": "melee", "difficulty": "impossible", "reason": "x",
        })


def test_apply_character_update_adjusts_health_and_armor():
    session = _session_with_character(health=7, max_health=10, armor=2)
    result = execute_tool(session, "apply_character_update", {
        "player_id": "p1", "health_delta": -3, "armor_delta": 1,
    })
    assert session.characters["p1"].health == 4
    assert session.characters["p1"].armor == 3
    assert result == {
        "player_id": "p1", "health": 4, "armor": 3,
        "unspent_skill_points": 0, "unspent_attribute_points": 0,
    }


def test_apply_character_update_clamps_health_to_max_and_zero():
    session = _session_with_character(health=9, max_health=10)
    execute_tool(session, "apply_character_update", {"player_id": "p1", "health_delta": 100})
    assert session.characters["p1"].health == 10

    execute_tool(session, "apply_character_update", {"player_id": "p1", "health_delta": -100})
    assert session.characters["p1"].health == 0


def test_apply_character_update_adds_and_removes_conditions_and_inventory():
    session = _session_with_character(conditions=["bleeding"], inventory=["stim pack"])
    execute_tool(session, "apply_character_update", {
        "player_id": "p1",
        "add_conditions": ["stunned"], "remove_conditions": ["bleeding"],
        "add_inventory": ["pistol"], "remove_inventory": ["stim pack"],
    })
    character = session.characters["p1"]
    assert character.conditions == ["stunned"]
    assert character.inventory == ["pistol"]


def test_apply_character_update_removing_absent_items_is_a_no_op():
    session = _session_with_character(conditions=[], inventory=[])
    execute_tool(session, "apply_character_update", {
        "player_id": "p1", "remove_conditions": ["not_present"], "remove_inventory": ["ghost item"],
    })
    assert session.characters["p1"].conditions == []
    assert session.characters["p1"].inventory == []


def test_apply_character_update_rejects_an_unknown_player_id():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        execute_tool(session, "apply_character_update", {"player_id": "ghost"})


def test_update_world_sets_location_and_mood():
    session = Session(session_id="s1")
    execute_tool(session, "update_world", {"location": "Watson district", "scene_mood": "tense"})
    assert session.location == "Watson district"
    assert session.scene_mood == "tense"


def test_update_world_leaves_unset_fields_unchanged():
    session = Session(session_id="s1")
    session.location = "Watson district"
    execute_tool(session, "update_world", {"scene_mood": "calm"})
    assert session.location == "Watson district"
    assert session.scene_mood == "calm"


def test_update_world_adds_and_removes_objectives():
    session = Session(session_id="s1")
    session.active_objectives = ["find the fixer"]
    execute_tool(session, "update_world", {
        "add_objectives": ["avoid corpo patrols"], "remove_objectives": ["find the fixer"],
    })
    assert session.active_objectives == ["avoid corpo patrols"]


def test_apply_character_update_grants_skill_points():
    session = _session_with_character()
    result = execute_tool(session, "apply_character_update", {
        "player_id": "p1", "skill_points_delta": 2,
    })
    assert session.characters["p1"].unspent_skill_points == 2
    assert result["unspent_skill_points"] == 2


def test_apply_character_update_grants_attribute_points():
    session = _session_with_character()
    result = execute_tool(session, "apply_character_update", {
        "player_id": "p1", "attribute_points_delta": 1,
    })
    assert session.characters["p1"].unspent_attribute_points == 1
    assert result["unspent_attribute_points"] == 1


def test_apply_character_update_rejects_an_out_of_range_milestone_grant():
    # Schema-bounded so one hallucinated large value can't max a character
    # in a single turn (ValidationError is a ValueError subclass).
    session = _session_with_character()
    with pytest.raises(ValueError):
        execute_tool(session, "apply_character_update", {
            "player_id": "p1", "attribute_points_delta": 50,
        })
    with pytest.raises(ValueError):
        execute_tool(session, "apply_character_update", {
            "player_id": "p1", "skill_points_delta": 99,
        })


def test_request_roll_skill_literal_matches_the_roster():
    # Pins RequestRoll.skill's Literal against ruleset.skills.SKILLS so the
    # two copies of the 14-skill roster can't silently drift: a name only in
    # the Literal is unreachable by the narrator, a name only in SKILLS
    # makes character.skills.get(tool.skill, 0) silently return 0 forever.
    skill_field = RequestRoll.model_fields["skill"]
    assert set(get_args(skill_field.annotation)) == set(SKILLS)


def test_unknown_tool_name_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown tool"):
        execute_tool(session, "nonsense", {})


def test_remember_npc_stores_a_fact():
    session = Session(session_id="s1")
    result = execute_tool(session, "remember_npc", {"name": "Jax", "fact": "offered the party a job"})
    assert session.npc_memory["Jax"] == ["offered the party a job"]
    assert result == {"name": "Jax", "facts": ["offered the party a job"]}


def test_remember_npc_appends_multiple_facts_for_the_same_npc():
    session = Session(session_id="s1")
    execute_tool(session, "remember_npc", {"name": "Jax", "fact": "first fact"})
    execute_tool(session, "remember_npc", {"name": "Jax", "fact": "second fact"})
    assert session.npc_memory["Jax"] == ["first fact", "second fact"]


def test_remember_npc_caps_facts_per_npc_dropping_the_oldest():
    session = Session(session_id="s1")
    for i in range(7):
        execute_tool(session, "remember_npc", {"name": "Jax", "fact": f"fact {i}"})
    assert session.npc_memory["Jax"] == ["fact 2", "fact 3", "fact 4", "fact 5", "fact 6"]


def test_remember_npc_evicts_the_least_recently_touched_npc_once_over_the_cap():
    session = Session(session_id="s1")
    for i in range(51):
        execute_tool(session, "remember_npc", {"name": f"npc{i}", "fact": "x"})
    assert len(session.npc_memory) == 50
    assert "npc0" not in session.npc_memory
    assert "npc50" in session.npc_memory


def test_remember_npc_touching_an_existing_npc_protects_it_from_eviction():
    session = Session(session_id="s1")
    for i in range(50):
        execute_tool(session, "remember_npc", {"name": f"npc{i}", "fact": "x"})
    # Touch npc0 again - it moves to most-recently-touched.
    execute_tool(session, "remember_npc", {"name": "npc0", "fact": "y"})
    # One more new NPC should now evict npc1 (the new least-recently-touched), not npc0.
    execute_tool(session, "remember_npc", {"name": "npc50", "fact": "x"})
    assert "npc0" in session.npc_memory
    assert "npc1" not in session.npc_memory


def test_remember_npc_rejects_a_fact_over_the_length_limit():
    session = Session(session_id="s1")
    with pytest.raises(ValueError):
        execute_tool(session, "remember_npc", {"name": "Jax", "fact": "x" * 500})


def test_remember_npc_rejects_a_name_over_the_length_limit():
    session = Session(session_id="s1")
    with pytest.raises(ValueError):
        execute_tool(session, "remember_npc", {"name": "x" * 500, "fact": "a fact"})


def test_roll_check_adds_chrome_bonus_and_social_penalty(monkeypatch):
    from engine.character import CharacterSheet
    from narrator.tools import roll_check

    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 5)
    rook = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid",
                          attributes={"reflexes": 10}, skills={"melee": 1}, chrome=["kama_blades"], humanity=30)
    assert roll_check(rook, "reflexes", "melee", "moderate")["skill_mod"] == 3        # 1 rank + 2 blades
    assert roll_check(rook, "presence", "persuasion", "moderate")["skill_mod"] == -1  # Slipping penalty


def test_roll_check_kagerou_keeps_higher_die_and_adds_bonus(monkeypatch):
    from engine.character import CharacterSheet
    from narrator.tools import roll_check

    rook = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid",
                          attributes={"reflexes": 10}, chrome=["kagerou"], humanity=90)
    dice = iter([3, 8])
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: next(dice))
    result = roll_check(rook, "reflexes", "stealth", "hard", overclock_id="kagerou")
    assert (result["first_die"], result["second_die"], result["die_result"]) == (3, 8, 8)
    assert result["overclock"] == "kagerou" and result["overclock_bonus"] == 2
    assert result["outcome"] == "failure"  # 8 + 0 + 0 + 2 = 10 < Hard 12

    dice = iter([3, 10])
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: next(dice))
    assert roll_check(rook, "reflexes", "stealth", "hard", overclock_id="kagerou")["outcome"] == "clean_success"


def test_offer_chrome_creates_an_offer_and_installs_nothing():
    from engine.character import CharacterSheet
    from engine.session import Session
    from narrator.tools import execute_tool

    session = Session(session_id="s")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    execute_tool(session, "offer_chrome", {"player_id": "p1", "item": "kagerou"})
    assert session.pending_chrome_offers == {"p1": "kagerou"}
    assert session.characters["p1"].chrome == []


def test_offer_chrome_rejects_unknown_item():
    import pytest
    from pydantic import ValidationError
    from engine.session import Session
    from narrator.tools import execute_tool

    with pytest.raises((ValueError, TypeError, ValidationError)):
        execute_tool(Session(session_id="s"), "offer_chrome", {"player_id": "p1", "item": "nope"})


def test_chrome_id_literal_matches_catalog():
    from narrator.tools import ChromeId
    from ruleset.cyberware import CHROME

    assert set(ChromeId.__args__) == set(CHROME)


def test_humanity_delta_is_bounded_and_applies():
    import pytest
    from pydantic import ValidationError
    from engine.character import CharacterSheet
    from engine.session import Session
    from narrator.tools import ApplyCharacterUpdate, execute_tool

    with pytest.raises(ValidationError):
        ApplyCharacterUpdate(player_id="p1", humanity_delta=6)
    with pytest.raises(ValidationError):
        ApplyCharacterUpdate(player_id="p1", humanity_delta=-1)
    session = Session(session_id="s")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", humanity=50)
    execute_tool(session, "apply_character_update", {"player_id": "p1", "humanity_delta": 5})
    assert session.characters["p1"].humanity == 55
