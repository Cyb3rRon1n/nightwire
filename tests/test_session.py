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


def test_session_world_state_starts_empty():
    session = Session(session_id="test-session")
    assert session.location is None
    assert session.scene_mood is None
    assert session.active_objectives == []


def test_two_sessions_do_not_share_mutable_objectives_list():
    a = Session(session_id="a")
    b = Session(session_id="b")
    a.active_objectives.append("find the fixer")
    assert b.active_objectives == []


def test_session_speaker_voices_defaults_to_empty_and_is_independent_per_instance():
    session_a = Session(session_id="a")
    session_b = Session(session_id="b")

    assert session_a.speaker_voices == {}
    session_a.speaker_voices["Jax"] = "am_adam"

    assert session_b.speaker_voices == {}


def test_session_narrative_summary_defaults_to_empty_and_is_independent_per_instance():
    session_a = Session(session_id="a")
    session_b = Session(session_id="b")

    assert session_a.narrative_summary == ""
    assert session_a.narrative_summary_line_count == 0
    session_a.narrative_summary = "The party met a fixer."
    session_a.narrative_summary_line_count = 12

    assert session_b.narrative_summary == ""
    assert session_b.narrative_summary_line_count == 0
