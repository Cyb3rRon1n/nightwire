import json

import pytest

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import ratings
from server.dispatch import handle_message
from server.narration import _build_messages, _drop_repeated_lines
from server.views import build_view
from tests.test_referee import _session


def _turn(s: Session, action: str, narration: str, location="Mama Sato's izakaya", present=("Mama Sato",)) -> None:
    s.location, s.present = location, list(present)
    s.log += [f"p1: {action}", narration]
    ratings.note_turn(s, f"PROMPT for {action}", action, narration)


def _rows() -> list[dict]:
    return [json.loads(line) for line in ratings.ratings_path().read_text().splitlines()]


def test_a_rating_is_saved_with_its_prompt_and_a_second_one_replaces_it():
    s = _session()
    _turn(s, "I order the eel.", "Mama Sato slides a bowl across the counter.")
    handle_message(s, {"type": "rate_turn", "like": False, "reason": "dull"}, "p1")
    handle_message(s, {"type": "rate_turn", "like": True}, "p1")
    rows = _rows()
    assert len(rows) == 1 and rows[0]["like"] is True and rows[0]["reason"] is None
    assert rows[0]["prompt"] == "PROMPT for I order the eel." and rows[0]["narration"].startswith("Mama Sato slides")
    assert build_view(s, "p1")["last_rating"] == {"like": True, "reason": None}
    _turn(s, "I pay.", "She counts the coins twice.")
    assert build_view(s, "p1")["last_rating"] is None  # a new turn starts unrated


def test_bad_ratings_are_refused():
    s = _session()
    with pytest.raises(ValueError):
        handle_message(s, {"type": "rate_turn", "like": True}, "p1")  # nothing narrated yet
    _turn(s, "I wait.", "Rain.")
    for msg in ({"type": "rate_turn"}, {"type": "rate_turn", "like": False, "reason": "rude"}):
        with pytest.raises(ValueError):
            handle_message(s, msg, "p1")


def test_the_narrator_sees_one_liked_turn_from_the_same_place_and_people_and_copies_are_cut():
    s = _session()
    _turn(s, "I ask about the rain.", "Neon bleeds into the puddles while the old radio hums a song nobody requests.")
    ratings.rate(s, True, None)
    _turn(s, "I go to the docks.", "Cranes groan over the black water of the yard.", "Kuroshio Docks", ())
    ratings.rate(s, True, None)
    s.log += ["filler"] * 25
    s.location, s.present = "Mama Sato's izakaya", ["Mama Sato"]
    prompt = _build_messages(s, "I sit.", 8192)[0]["content"]
    assert ratings.EXAMPLE_HEADER + "\nI ask about the rain. → Neon bleeds" in prompt and "Cranes groan" not in prompt
    from narrator.client import NarrationSegment

    class reply:
        narration = [NarrationSegment(speaker="narrator", text=(
            "Neon bleeds into the puddles while the old radio hums a song nobody requests. Mama Sato nods."))]
    _drop_repeated_lines(reply, s)
    assert reply.narration[0].text == "Mama Sato nods."


def test_a_turn_still_in_the_recent_log_is_not_shown():
    s = _session()
    _turn(s, "I ask about the rain.", "Neon bleeds into the puddles.")
    ratings.rate(s, True, None)
    assert ratings.example_block(s) == ("", [])


def test_the_avoid_line_needs_a_reason_twice():
    s = _session()
    for i, reason in enumerate(["acted_for_me", "dull", "acted_for_me"]):
        _turn(s, f"I wait {i}.", f"Turn {i}.")
        ratings.rate(s, False, reason)
        if i == 1:
            assert ratings.avoid_line() == ""
    assert ratings.avoid_line() == "The player has disliked: deciding what they do."
    assert "The player has disliked: deciding what they do." in _build_messages(s, "I sit.", 8192)[0]["content"]


def test_check_ins_come_only_in_calm_stretches_and_not_too_often():
    s = _session()
    for i in range(9):
        _turn(s, f"I walk {i}.", "Quiet.")
        ratings.maybe_checkin(s)
    assert not s.checkin_open  # too early
    _turn(s, "I roll the dice.", "Tense.")
    s.log.append('[roll: {"total": 12}]')
    ratings.maybe_checkin(s)
    assert not s.checkin_open  # a roll in the last 3 turns
    for i in range(3):
        _turn(s, f"I rest {i}.", "Quiet.")
    ratings.maybe_checkin(s)
    assert s.checkin_open and build_view(s, "p1")["checkin"] is True
    handle_message(s, {"type": "dismiss_checkin"}, "p1")
    assert not s.checkin_open
    for i in range(19):
        _turn(s, f"I idle {i}.", "Quiet.")
        ratings.maybe_checkin(s)
        assert not s.checkin_open
    _turn(s, "I idle more.", "Quiet.")
    ratings.maybe_checkin(s)
    assert s.checkin_open
    ratings.rate(s, True, None)
    assert not s.checkin_open and _rows()[-1]["checkin"] is True


def test_old_saves_load(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    for k in ("last_turn", "last_rating", "checkin_open", "checkin_turn"):
        del data[k]
    path.write_text(json.dumps(data))
    loaded = store.load("old")
    assert loaded.last_turn is None and loaded.checkin_open is False and loaded.checkin_turn is None
