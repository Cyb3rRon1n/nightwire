from unittest.mock import patch

from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import (
    advance_turn,
    current_turn,
    end_combat,
    is_players_turn,
    join,
    roll_initiative,
    start_combat,
)


def _character(player_id: str, name: str = "Rook", reflexes: int = 10) -> CharacterSheet:
    return CharacterSheet(
        player_id=player_id, name=name, role="solo", lifepath="streetkid", attributes={"reflexes": reflexes}
    )


def test_join_adds_the_character_and_the_turn_order():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    assert "p1" in session.characters
    assert "p1" in session.turn_order


def test_join_is_safe_to_call_again_for_a_reconnecting_player():
    # A rejoining player shouldn't get a duplicate turn_order slot.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p1"))
    assert session.turn_order.count("p1") == 1


def test_rejoining_does_not_reset_a_live_characters_state():
    # The reconnect path must not silently overwrite mid-session damage or
    # loot with a fresh CharacterSheet - a real bug the count-only test
    # above didn't catch.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    session.characters["p1"].health = 3
    session.characters["p1"].inventory.append("stim pack")

    join(session, _character("p1"))  # reconnect with a fresh sheet

    assert session.characters["p1"].health == 3
    assert session.characters["p1"].inventory == ["stim pack"]


def test_current_turn_is_none_outside_combat():
    # The spec's own headline decision: no turn concept applies at all
    # outside combat, regardless of who's joined.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    assert current_turn(session) is None


def test_current_turn_is_none_with_no_players_joined():
    session = Session(session_id="test-session")
    assert current_turn(session) is None


def test_is_players_turn_is_always_true_outside_combat():
    # Free-flowing action: anyone may act at any time when not in combat.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    assert is_players_turn(session, "p1") is True
    assert is_players_turn(session, "p2") is True


def test_is_players_turn_is_true_even_for_an_unrecognized_player_outside_combat():
    # Free-flowing means free-flowing - outside combat there's no roster
    # check either, matching "no turn concept applies at all."
    session = Session(session_id="test-session")
    assert is_players_turn(session, "someone-not-joined") is True


def test_start_combat_orders_turn_order_by_initiative_descending():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    assert session.turn_order == ["p2", "p1"]
    assert session.in_combat is True
    assert session.current_turn_index == 0


def test_start_combat_is_idempotent():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    start_combat(session, {"p1": 99, "p2": 1})  # would flip the order if re-run
    assert session.turn_order == ["p2", "p1"]


def test_current_turn_and_is_players_turn_during_combat():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    assert current_turn(session) == "p2"
    assert is_players_turn(session, "p2") is True
    assert is_players_turn(session, "p1") is False


def test_advance_turn_cycles_through_the_order():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    advance_turn(session)
    assert current_turn(session) == "p1"
    advance_turn(session)
    assert current_turn(session) == "p2"  # wraps back around


def test_advance_turn_outside_combat_is_a_no_op():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    advance_turn(session)  # not in combat - nothing to advance
    assert session.current_turn_index == 0


def test_end_combat_restores_the_pre_combat_join_order():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})  # reorders to [p2, p1]
    end_combat(session)
    assert session.turn_order == ["p1", "p2"]  # restored to join order
    assert session.in_combat is False
    assert session.pre_combat_turn_order is None


def test_end_combat_appends_a_mid_combat_joiner_at_the_end():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    join(session, _character("p3"))  # joins mid-combat, appended live to turn_order
    end_combat(session)
    assert session.turn_order == ["p1", "p2", "p3"]


def test_end_combat_is_idempotent():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    end_combat(session)  # never in combat - no-op, no error
    assert session.in_combat is False


def test_roll_initiative_adds_the_reflexes_modifier():
    session = Session(session_id="test-session")
    join(session, _character("p1", reflexes=16))  # +3 modifier
    with patch("engine.turns.random.randint", return_value=7):
        total = roll_initiative(session, "p1")
    assert total == 10


def test_roll_initiative_does_not_lock_combat_until_everyone_has_rolled():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    roll_initiative(session, "p1")
    assert session.in_combat is False
    assert "p1" in session.pending_initiative


def test_roll_initiative_locks_combat_once_the_whole_roster_has_rolled():
    session = Session(session_id="test-session")
    join(session, _character("p1", reflexes=8))  # -1 modifier
    join(session, _character("p2", reflexes=16))  # +3 modifier
    with patch("engine.turns.random.randint", side_effect=[5, 5]):
        roll_initiative(session, "p1")  # 5 - 1 = 4
        roll_initiative(session, "p2")  # 5 + 3 = 8
    assert session.in_combat is True
    assert session.turn_order == ["p2", "p1"]
    assert session.pending_initiative == {}


def test_roll_initiative_locks_immediately_for_a_solo_session():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    roll_initiative(session, "p1")
    assert session.in_combat is True


def test_roll_initiative_is_a_no_op_for_a_player_who_already_rolled():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    first = roll_initiative(session, "p1")
    second = roll_initiative(session, "p1")
    assert second is None
    assert session.pending_initiative["p1"] == first


def test_roll_initiative_is_a_no_op_once_combat_is_already_underway():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    start_combat(session, {"p1": 8})

    result = roll_initiative(session, "p1")

    assert result is None
    assert session.pending_initiative == {}


def test_end_combat_clears_a_pending_declaration_even_if_combat_never_started():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    roll_initiative(session, "p1")  # p2 hasn't rolled yet - declaration is pending

    end_combat(session)

    assert session.pending_initiative == {}
