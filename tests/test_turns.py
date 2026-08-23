from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, current_turn, end_combat, is_players_turn, join, start_combat


def _character(player_id: str, name: str = "Rook") -> CharacterSheet:
    return CharacterSheet(player_id=player_id, name=name, role="solo", lifepath="streetkid")


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
