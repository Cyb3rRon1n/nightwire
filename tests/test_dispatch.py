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

    handle_message(session, message)

    assert session.characters["p1"].name == "Rook"
    assert "p1" in session.turn_order


def test_join_reconnect_does_not_reset_live_state():
    session = Session(session_id="s1")
    join_message = {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }
    handle_message(session, join_message)
    session.characters["p1"].health = 3

    handle_message(session, join_message)

    assert session.characters["p1"].health == 3


def test_start_combat_orders_turn_order_by_initiative():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    })
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    })

    handle_message(session, {
        "type": "start_combat",
        "initiative_rolls": {"p1": 5, "p2": 12},
    })

    assert session.in_combat is True
    assert session.turn_order == ["p2", "p1"]


def test_advance_turn_cycles_the_order():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    })
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    })
    handle_message(session, {"type": "start_combat", "initiative_rolls": {"p1": 5, "p2": 12}})

    handle_message(session, {"type": "advance_turn"})

    assert session.current_turn_index == 1


def test_end_combat_restores_pre_combat_order():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    })
    handle_message(session, {"type": "start_combat", "initiative_rolls": {"p1": 5}})

    handle_message(session, {"type": "end_combat"})

    assert session.in_combat is False


def test_unknown_message_type_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown message type"):
        handle_message(session, {"type": "nonsense"})


def test_missing_type_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'type'"):
        handle_message(session, {})


def test_join_missing_character_field_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'character'"):
        handle_message(session, {"type": "join"})


def test_start_combat_missing_initiative_rolls_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'initiative_rolls'"):
        handle_message(session, {"type": "start_combat"})
