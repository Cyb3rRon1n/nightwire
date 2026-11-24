import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import director, promises
from server.narration import _build_messages
from tests.test_referee import _session


def _turn(s: Session, roll: str | None = None) -> int:
    s.log.append("p1: I keep going.")
    if roll:
        s.log.append(f"[roll: {json.dumps({'outcome': roll})}]")
    return s.characters["p1"].health


def test_tension_rises_with_rolls_failures_hurt_and_combat_and_falls_when_calm():
    s = _session()
    director.tick(s, "p1", _turn(s, "clean_success"))
    assert s.tension == 2
    director.tick(s, "p1", _turn(s, "failure"))
    assert s.tension == 6
    hp = _turn(s)
    s.characters["p1"].health -= 10
    director.tick(s, "p1", hp)
    assert s.tension == 8 - 3  # peak reached: a breather starts and the peak is spent
    director.tick(s, "p1", _turn(s))
    assert s.tension == 4
    s.in_combat = True
    director.tick(s, "p1", _turn(s))
    assert s.tension == 7


def test_the_set_up_turn_of_a_roll_does_not_count():
    s = _session()
    s.pending_rolls["p1"] = {"skill": "athletics"}
    director.tick(s, "p1", _turn(s))
    assert (s.tension, s.quiet_turns) == (0, 0)


def test_a_breather_lasts_two_turns_and_shows_in_the_prompt():
    s = _session()
    s.location = "Ikebe Low"
    s.tension = 7
    director.tick(s, "p1", _turn(s, "failure"))
    assert s.breather == 2
    assert director.PACING in _build_messages(s, "I catch my breath.", 8192)[-1]["content"]
    director.tick(s, "p1", _turn(s))
    director.tick(s, "p1", _turn(s))
    assert s.breather == 0
    assert director.PACING not in _build_messages(s, "I walk on.", 8192)[-1]["content"]


def test_a_quiet_spell_fires_one_district_event_and_its_lead_becomes_an_objective():
    s = _session()
    s.location = "Kuroshio Docks"
    for _ in range(4):
        director.tick(s, "p1", _turn(s))
    assert len(s.pending_world_events) == 1
    event = next(e for e in director.events() if e["text"] == s.pending_world_events[0])
    assert "Kuroshio Docks" in event["where"]
    assert event["lead"] in s.active_objectives
    s.pending_world_events.clear()
    for _ in range(4):  # quiet again, but within 6 turns of the last event
        director.tick(s, "p1", _turn(s))
    assert s.pending_world_events == []


def test_calm_turns_after_a_breather_count_toward_a_quiet_spell():
    s = _session()
    s.location = "Kuroshio Docks"
    s.tension = 7
    director.tick(s, "p1", _turn(s, "failure"))
    assert (s.breather, s.tension) == (2, 5)
    for _ in range(3):
        director.tick(s, "p1", _turn(s))
    assert s.pending_world_events == []
    director.tick(s, "p1", _turn(s))  # the fourth calm turn in a row, breather over
    assert len(s.pending_world_events) == 1


def test_state_tied_events_come_first_and_fill_in_the_oldest_promise():
    s = _session()
    s.location = "Nowhere in particular"
    promises.record(s, "Mama Sato", "find Kenta")
    event = director.pick(s, "p1")
    assert event["id"] == "asking-after"
    director.fire(s, event)
    assert s.pending_world_events == ["Someone mentions Mama Sato - they were asking after you, and about find Kenta."]


def test_debt_events_need_debt():
    s = _session()
    s.location = "Ikebe Low"
    s.stretch = 3  # the night clock: the torite van works the small hours
    assert director.pick(s, "p1")["id"] != "torite-van"
    s.characters["p1"].installments_owed = 2
    assert director.pick(s, "p1")["id"] == "torite-van"


def test_no_event_repeats_within_forty_turns():
    s = _session()
    s.location = "Yomi Line"
    director.fire(s, director.pick(s, "p1"))
    assert director.pick(s, "p1")["id"] != "yomi-lantern"
    s.log += ["p1: I wait."] * 40
    assert director.pick(s, "p1")["id"] == "yomi-lantern"


def test_every_generic_event_has_a_lead():
    for e in director.events():
        assert e.get("lead") or e.get("needs"), e["id"]


def test_old_saves_load_with_a_calm_director(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    for key in ("tension", "breather", "quiet_turns", "events_used"):
        data.pop(key)
    path.write_text(json.dumps(data))
    s = store.load("old")
    assert (s.tension, s.breather, s.quiet_turns, s.events_used) == (0, 0, 0, {})


def test_a_player_without_a_character_is_ignored_and_no_calm_note_in_a_fight():
    s = _session()
    director.tick(s, "nobody", 0)
    assert s.tension == 0
    s.breather, s.in_combat = 2, True
    assert director.pacing_line(s) == ""


def test_tick_moves_pressure_clocks_and_the_prompt_shows_shown_ones_here():
    s = _session()
    s.location = "Kuroshio Docks"
    s.log.append("p1: I look around.")
    director.tick(s, "p1", s.characters["p1"].health)
    s.log.append("p1: I swing at the guard.")
    s.log.append(f"[roll: {json.dumps({'outcome': 'clean_success', 'skill': 'melee'})}]")
    director.tick(s, "p1", s.characters["p1"].health)
    assert s.clocks["ogane-docks"]["filled"] == 1
    assert "Pressure: Ōgane crackdown on the Docks 1/6." in _build_messages(s, "I walk on.", 8192)[-1]["content"]
    s.clocks["ogane-docks"]["filled"], s.clocks["container"]["filled"] = 0, 2
    assert "Pressure:" not in _build_messages(s, "I walk on.", 8192)[-1]["content"]
