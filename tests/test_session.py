from engine.character import CharacterSheet
from engine.session import Session


def test_session_starts_empty():
    session = Session(session_id="test-session")
    assert session.characters == {}
    assert session.turn_order == []
    assert session.current_turn_index == 0
    assert session.in_combat is False
    assert session.pre_combat_turn_order is None
    assert session.log == []


def test_session_can_hold_characters():
    session = Session(session_id="test-session")
    rook = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    session.characters["p1"] = rook
    assert session.characters["p1"] is rook


def test_two_sessions_do_not_share_mutable_default_state():
    a = Session(session_id="a")
    b = Session(session_id="b")
    a.turn_order.append("p1")
    a.log.append("something happened")
    assert b.turn_order == []
    assert b.log == []
