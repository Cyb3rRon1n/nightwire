from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import current_turn, is_players_turn, join


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
