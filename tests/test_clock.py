import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import clock, director
from narrator.cast import refresh
from narrator.referee import apply_verdict
from tests.test_referee import _session


def _turns(s: Session, n: int, location: str | None = None) -> None:
    for _ in range(n):
        s.log.append("p1: I wait.")
        if location:
            s.location = location
        clock.tick(s)


def test_three_turns_move_the_night_on_one_stretch():
    s = _session()
    _turns(s, 2)
    assert clock.stretch(s) == "evening"
    _turns(s, 1)
    assert (s.night, clock.stretch(s)) == (1, "last train")
    assert "[clock: night 1, last train]" in s.log


def test_a_ride_to_another_district_costs_a_stretch():
    s = _session()
    _turns(s, 1, "Ikebe Low")
    _turns(s, 1, "Kuroshio Docks")
    assert clock.stretch(s) == "last train"


def test_sleep_jumps_to_the_next_evening_and_the_turn_after_does_not_move_it():
    s = _session()
    _turns(s, 7)
    apply_verdict(s, "p1", {"human_moment": "none", "went_to_sleep": True})
    clock.tick(s)
    assert (s.night, clock.stretch(s)) == (2, "evening")


def test_after_first_train_the_next_night_begins_with_a_daybreak_event():
    s = _session()
    _turns(s, 15)
    assert (s.night, clock.stretch(s)) == (2, "evening")
    assert clock.DAYBREAK in s.pending_world_events


def test_the_narrator_is_told_the_time_no_trains_and_who_sleeps():
    s = _session()
    s.stretch = 3
    assert clock.line(s).startswith("Time: night 1, small hours (")
    assert "No Ring Line trains" in clock.line(s)
    s.stretch = 4
    assert "Mama Sato" in clock.line(s)


def test_an_asleep_npc_is_not_in_the_cast():
    s = Session(session_id="s", location="Ikebe Low")
    s.stretch = 4  # first train: the izakaya shuts
    s.location = "Mama Sato's izakaya"
    refresh(s, "I walk to the izakaya.")
    assert "Mama Sato" not in s.present


def test_sleep_needs_sleep_in_the_action():
    from narrator.referee import ground
    s = _session()
    assert ground(s, {"went_to_sleep": True}, "I rest a moment on the bench.", "You sit.")["went_to_sleep"] is False
    assert ground(s, {"went_to_sleep": True}, "I go home to my room and sleep.", "You sleep.")["went_to_sleep"]


def test_an_asleep_keeper_is_back_when_the_player_arrives_awake_hours_and_a_named_one_stays():
    s = Session(session_id="s", location="Ikebe Low")
    s.stretch = 1  # last train: Old Hara naps
    s.location = "Old Hara's clinic"
    refresh(s, "I knock and wake Old Hara.")
    assert "Old Hara" in s.present  # the action names him
    s.stretch = 2
    refresh(s, "I sit down.")  # same place: nobody vanishes or reappears mid-scene
    assert "Old Hara" in s.present


def test_an_event_fires_only_in_its_stretches():
    s = _session()
    van = next(e for e in director.events() if e["id"] == "torite-van")
    assert "small hours" in van["stretches"]
    s.characters["p1"].installments_owed = 3
    s.location = "Ikebe Low"
    assert director.pick(s, "p1")["id"] != "torite-van"  # evening
    s.stretch = 3
    assert director.pick(s, "p1")["id"] == "torite-van"


def test_old_saves_load_at_night_one_evening(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    s = _session()
    store.save(s)
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    for k in ("night", "stretch", "stretch_start", "clock_district"):
        data.pop(k)
    path.write_text(json.dumps(data))
    loaded = store.load(s.session_id)
    assert (loaded.night, clock.stretch(loaded)) == (1, "evening")
    loaded.log += ["p1: I wait."] * 20  # a long game from before the clock
    clock.tick(loaded)
    assert clock.stretch(loaded) == "evening"  # its first turn starts the stretch, it doesn't jump one
