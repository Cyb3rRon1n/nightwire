import pytest

from engine.character import CharacterSheet
from engine.session import Session
from narrator.tools import execute_tool


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
        "player_id": "p1", "attribute": "reflexes", "skill_mod": 0, "difficulty": "easy", "reason": "dodge",
    })
    assert result["attribute_mod"] == 3  # modifier(16) == (16 - 10) // 2 == 3


def test_request_roll_clamps_skill_mod_to_a_plausible_range():
    session = _session_with_character()
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "body", "skill_mod": 999, "difficulty": "easy", "reason": "x",
    })
    assert result["skill_mod"] == 5


def test_request_roll_rejects_an_unknown_player_id():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        execute_tool(session, "request_roll", {
            "player_id": "ghost", "attribute": "body", "skill_mod": 0, "difficulty": "easy", "reason": "x",
        })


def test_request_roll_rolls_a_real_die_and_resolves_the_outcome():
    session = _session_with_character(attributes={"reflexes": 14})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill_mod": 2, "difficulty": "easy", "reason": "climbing a wall",
    })
    assert 1 <= result["die_result"] <= 10
    assert result["dc"] == 8
    assert result["outcome"] in ("clean_success", "complication", "failure")


def test_request_roll_rejects_an_unknown_difficulty():
    session = _session_with_character()
    with pytest.raises(ValueError):
        execute_tool(session, "request_roll", {
            "player_id": "p1", "attribute": "body", "skill_mod": 0, "difficulty": "impossible", "reason": "x",
        })


def test_apply_character_update_adjusts_health_and_armor():
    session = _session_with_character(health=7, max_health=10, armor=2)
    result = execute_tool(session, "apply_character_update", {
        "player_id": "p1", "health_delta": -3, "armor_delta": 1,
    })
    assert session.characters["p1"].health == 4
    assert session.characters["p1"].armor == 3
    assert result == {"player_id": "p1", "health": 4, "armor": 3}


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


def test_start_combat_tool_never_mutates_session_state():
    session = Session(session_id="s1")
    result = execute_tool(session, "start_combat", {"reason": "ambush"})
    assert session.in_combat is False
    assert "note" in result


def test_end_combat_tool_never_mutates_session_state():
    session = Session(session_id="s1")
    session.in_combat = True
    result = execute_tool(session, "end_combat", {"reason": "enemies fled"})
    assert session.in_combat is True
    assert "note" in result


def test_unknown_tool_name_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown tool"):
        execute_tool(session, "nonsense", {})
