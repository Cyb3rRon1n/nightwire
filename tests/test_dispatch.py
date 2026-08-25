import pytest

from engine.session import Session
from server.dispatch import handle_message


def test_join_creates_a_character_and_adds_it_to_turn_order():
    session = Session(session_id="s1")
    message = {
        "type": "join",
        "character": {
            "player_id": "p1",
            "name": "Rook",
            "role": "solo",
            "lifepath": "streetkid",
        },
    }

    handle_message(session, message, "p1")

    assert session.characters["p1"].name == "Rook"
    assert "p1" in session.turn_order


def test_join_reconnect_does_not_reset_live_state():
    session = Session(session_id="s1")
    join_message = {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }
    handle_message(session, join_message, "p1")
    session.characters["p1"].health = 3

    handle_message(session, join_message, "p1")

    assert session.characters["p1"].health == 3


def test_roll_initiative_locks_combat_once_the_whole_roster_has_rolled():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    }, "p2")

    handle_message(session, {"type": "roll_initiative"}, "p1")
    assert session.in_combat is False  # p2 hasn't rolled yet

    handle_message(session, {"type": "roll_initiative"}, "p2")
    assert session.in_combat is True
    assert set(session.turn_order) == {"p1", "p2"}
    assert any(line.startswith("[initiative: Rook rolled") for line in session.log)
    assert any(line.startswith("[initiative: Ghost rolled") for line in session.log)


def test_roll_initiative_for_unjoined_player_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        handle_message(session, {"type": "roll_initiative"}, "p1")


def test_advance_turn_cycles_the_order():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    }, "p2")
    handle_message(session, {"type": "roll_initiative"}, "p1")
    handle_message(session, {"type": "roll_initiative"}, "p2")

    handle_message(session, {"type": "advance_turn"}, "p1")

    assert session.current_turn_index == 1


def test_end_combat_restores_pre_combat_order():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")
    handle_message(session, {"type": "roll_initiative"}, "p1")

    handle_message(session, {"type": "end_combat"}, "p1")

    assert session.in_combat is False


def test_unknown_message_type_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown message type"):
        handle_message(session, {"type": "nonsense"}, "p1")


def test_missing_type_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'type'"):
        handle_message(session, {}, "p1")


def test_join_missing_character_field_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'character'"):
        handle_message(session, {"type": "join"}, "p1")


def test_join_accepts_a_valid_starting_skill_allocation():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "skills": {"stealth": 2, "hacking": 1},
        },
    }, "p1")

    character = session.characters["p1"]
    assert character.skills == {"stealth": 2, "hacking": 1}
    assert character.unspent_skill_points == 5  # 8 - 3 spent


def test_join_rejects_a_starting_allocation_over_budget():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="exceed the starting budget"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"melee": 3, "athletics": 3, "stealth": 3},  # 9 > budget of 8
            },
        }, "p1")


def test_join_rejects_a_starting_allocation_over_the_governing_attribute_cap():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="exceeds cap"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"melee": 4},  # attribute defaults to 10 -> cap 3, 4 > 3
            },
        }, "p1")


def test_join_rejects_an_unknown_skill_name():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown skill"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"lockpicking": 1},
            },
        }, "p1")


def test_join_rejects_a_negative_skill_rank():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="cannot be negative"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"stealth": -1},
            },
        }, "p1")


def test_join_with_no_skills_field_leaves_the_full_budget_unspent():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    assert session.characters["p1"].skills == {}
    assert session.characters["p1"].unspent_skill_points == 8


def test_allocate_skill_points_increases_rank_and_decreases_unspent():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    handle_message(session, {"type": "allocate_skill_points", "skill": "hacking", "amount": 2}, "p1")

    character = session.characters["p1"]
    assert character.skills["hacking"] == 2
    assert character.unspent_skill_points == 6


def test_allocate_skill_points_rejects_insufficient_points():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "skills": {"hacking": 3, "engineering": 3, "melee": 2},
        },
    }, "p1")
    # all 8 points already spent, 0 unspent left

    with pytest.raises(ValueError, match="insufficient skill points"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "stealth", "amount": 1}, "p1")


def test_allocate_skill_points_rejects_exceeding_the_governing_attribute_cap():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "skills": {"hacking": 3},
        },
    }, "p1")
    # hacking is already at its cap of 3 (attribute defaults to 10)

    with pytest.raises(ValueError, match="would exceed cap"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "hacking", "amount": 1}, "p1")


def test_allocate_skill_points_rejects_an_unknown_skill():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    with pytest.raises(ValueError, match="unknown skill"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "lockpicking", "amount": 1}, "p1")


def test_allocate_skill_points_for_unjoined_player_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "hacking", "amount": 1}, "ghost")
