import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import clock, director
from narrator.cast import refresh
from narrator.referee import apply_verdict
from engine.character import CharacterSheet
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


def _party() -> Session:
    s = _session()
    s.characters["p2"] = CharacterSheet(player_id="p2", name="Ghost", role="netrunner", lifepath="streetkid",
                                        attributes={}, humanity=50)
    return s


def test_a_party_spends_a_stretch_per_three_rounds_not_three_turns():
    s = _party()
    for _ in range(3):
        s.log += ["p1: I wait.", "p2: I wait."]
        clock.tick(s)
    assert clock.stretch(s) == "last train"
    s = _party()
    s.log += ["p1: I wait.", "p2: I wait.", "p1: I wait."]
    clock.tick(s)
    assert clock.stretch(s) == "evening"


def test_the_night_jumps_only_when_the_whole_party_sleeps():
    s = _party()
    apply_verdict(s, "p1", {"human_moment": "none", "went_to_sleep": True})
    assert (s.night, s.sleepers) == (1, ["p1"])
    apply_verdict(s, "p1", {"human_moment": "none"})  # p1 gets up again
    apply_verdict(s, "p2", {"human_moment": "none", "went_to_sleep": True})
    assert s.night == 1
    apply_verdict(s, "p1", {"human_moment": "none", "went_to_sleep": True})
    assert (s.night, clock.stretch(s), s.sleepers) == (2, "evening", [])


def test_a_scheduled_npc_is_at_their_place_in_their_stretch():
    s = Session(session_id="s", location="Hanabira-chō")
    s.stretch = 3  # small hours: Jun counts the take in the pachinko back room
    s.location = "Pachinko back room"
    refresh(s, "I push through the bead curtain.")
    assert "Jun Arakawa" in s.present
    s = Session(session_id="s", location="Hanabira-chō")
    s.stretch = 3
    s.location = "Jun Arakawa's karaoke box"
    refresh(s, "I knock on the door.")
    assert "Jun Arakawa" not in s.present
    s.stretch, s.cast_location = 0, None  # evening: back in his box
    refresh(s, "I knock on the door.")
    assert "Jun Arakawa" in s.present


def test_asking_where_someone_is_tells_the_narrator_their_usual_place():
    s = _session()
    s.stretch = 2
    usual = clock.whereabouts(s, "I ask where Jun Arakawa hangs out this late.")
    assert usual == "If asked: Jun Arakawa is usually at the Pachinko back room in the small hours."
    assert clock.whereabouts(s, "I ask about Jun.") is None


def test_waiting_until_a_stretch_lands_there_and_a_past_one_is_tomorrow():
    s = _session()
    s.stretch = 1
    assert clock.wait(s, "I wait until the small hours.").startswith("You waited until small hours")
    assert (s.night, clock.stretch(s)) == (1, "small hours")
    clock.wait(s, "I kill time until evening.")
    assert (s.night, clock.stretch(s)) == (2, "evening") and clock.DAYBREAK in s.pending_world_events
    clock.wait(s, "I lie low a while.")
    assert clock.stretch(s) == "last train"


def test_a_moment_is_not_a_wait_and_a_fight_refuses_one():
    s = _session()
    assert clock.wait(s, "I wait for her answer.") is None and clock.stretch(s) == "evening"
    s.in_combat = True
    assert "fight" in clock.wait(s, "I wait until dawn.") and clock.stretch(s) == "evening"


def test_schedules_must_name_world_npcs_stretches_and_place_cards(tmp_path, monkeypatch):
    import pytest
    bad = tmp_path / "hours.toml"
    bad.write_text('[asleep]\n[where."Jun Arakawa"]\n"small hours" = "Somewhere made up"\n')
    monkeypatch.setattr(clock, "_HOURS_PATH", bad)
    clock._where_table.cache_clear()
    with pytest.raises(ValueError):
        clock._where_table()
    clock._where_table.cache_clear()


def test_waits_the_player_did_not_ask_for_move_nothing():
    # Review 2026-11-23: each of these skipped time.
    s = _session()
    for action in ("I can't wait to hit the club after shutters.", "Wait, what? The first train?",
                   "I hang around the bar and chat with Mama Sato.", "I tell her to wait, I'll be back in an hour.",
                   "I don't wait for shutters."):
        assert clock.wait(s, action) is None, action
    assert clock.stretch(s) == "evening"
    s.stretch = 1
    clock.wait(s, "I wait out the evening crowd until the small hours.")  # the stretch after "until", not table order
    assert (s.night, clock.stretch(s)) == (1, "small hours")


def test_waiting_in_place_brings_in_who_keeps_these_hours_and_a_ride_is_not_counted_twice():
    s = _session()
    s.stretch, s.location = 1, "Pachinko back room"
    refresh(s, "I sit down.")
    assert "Jun Arakawa" not in s.present
    s.clock_district = "Ikebe Low"  # rode in from Ikebe Low this turn
    clock.wait(s, "I wait until the small hours.")
    refresh(s, "I wait until the small hours.")
    assert "Jun Arakawa" in s.present
    s.log.append("p1: I wait until the small hours.")
    clock.tick(s)
    assert clock.stretch(s) == "small hours"


def test_asking_where_matches_whole_names_only():
    s = _session()
    assert clock.whereabouts(s, "Where are you headed tomorrow?") is None  # not Moro
    assert clock.whereabouts(s, "Where is the junk yard?") is None  # not Jun


def test_a_scheduled_keeper_on_stage_stays_when_their_stretch_ends():
    s = _session()
    s.stretch, s.location = 1, "Courier depot"
    refresh(s, "I look for Hachi.")
    assert "Hachi" in s.present
    s.stretch = 2  # shutters down: she's at the pier now, but not mid-conversation
    refresh(s, "I keep talking.")
    assert "Hachi" in s.present
