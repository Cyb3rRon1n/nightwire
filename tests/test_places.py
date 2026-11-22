import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import director, places
from narrator.referee import apply_verdict, ground
from server.narration import _build_messages
from server.views import build_view
from tests.test_referee import _session


def _turn(s: Session, roll: dict | None = None) -> int:
    s.log.append("p1: I keep going.")
    if roll:
        s.log.append(f"[roll: {json.dumps(roll)}]")
    return s.characters["p1"].health


def _here(s: Session) -> dict:
    return s.places[places.key(s)]


def test_a_fight_heats_the_place_and_cools_while_away():
    s = _session()
    s.location = "Ikebe Low"
    hp = _turn(s, {"skill": "melee", "outcome": "clean_success"})
    s.characters["p1"].health -= 5
    director.tick(s, "p1", hp)
    assert _here(s)["heat"] == places.FIGHT + places.HURT
    assert _here(s)["warmth"] == -1
    s.location = "Kuroshio Docks"
    for _ in range(10):
        director.tick(s, "p1", _turn(s))
    s.location = "Ikebe Low"
    director.tick(s, "p1", _turn(s))
    assert s.places["Ikebe Low"]["heat"] == 2


def test_heat_nine_locks_the_district_down_and_cools_to_five():
    s = _session()
    s.location = "Kuroshio Docks"
    s.places["Kuroshio Docks"] = {"heat": 7, "warmth": 0, "marks": [], "last_visit": 0, "warmed": -1}
    s.in_combat = True
    director.tick(s, "p1", _turn(s))
    assert _here(s)["heat"] == places.LOCKDOWN_AFTER
    assert s.pending_world_events[-1].startswith("Ōgane Heavy sweeps Kuroshio Docks")
    assert "Lie low until the Ōgane sweep moves on" in s.active_objectives


def test_a_mark_is_grounded_kept_and_stays_for_good_if_seen_again():
    s = _session()
    s.location = "Ikebe Low"
    apply_verdict(s, "p1", ground(s, {"left_mark": "smashed noodle stall"}, "I kick the stall.",
                                  "The noodle stall cracks and folds, smashed."))
    apply_verdict(s, "p1", ground(s, {"left_mark": "burning car"}, "I wait.", "Nothing happens."))
    assert [m["text"] for m in _here(s)["marks"]] == ["smashed noodle stall"]
    s.location = "Kuroshio Docks"
    for _ in range(5):
        director.tick(s, "p1", _turn(s))
    s.location = "Ikebe Low"
    director.tick(s, "p1", _turn(s))
    assert _here(s)["marks"][0]["permanent"]
    s.log += ["p1: I wait."] * 100
    director.tick(s, "p1", _turn(s))
    assert _here(s)["marks"]


def test_an_unseen_mark_fades_and_only_three_are_kept():
    s = _session()
    s.location = "Ikebe Low"
    for text in ("one", "two", "three", "four"):
        places.mark(s, text)
    assert [m["text"] for m in _here(s)["marks"]] == ["two", "three", "four"]
    s.log += ["p1: I wait."] * 31
    places.arrive(s)
    assert _here(s)["marks"] == []


def test_kindness_warms_a_place_one_step_a_turn():
    s = _session()
    s.location = "Ikebe Low"
    apply_verdict(s, "p1", {"human_moment": "big"})
    apply_verdict(s, "p1", {"human_moment": "big"})
    assert _here(s)["warmth"] == 1
    assert places.mood(_here(s)) == "friendly"


def test_the_narrator_and_the_player_see_the_place():
    s = _session()
    s.location = "Ikebe Low"
    s.log = ["p1: I kick the stall."]
    places.mark(s, "smashed noodle stall")
    _here(s)["heat"] = 4
    prompt = _build_messages(s, "I look around.", 8192)[-1]["content"]
    assert "This place: smashed noodle stall (Rook, 0 turns ago); people here are wary." in prompt
    assert build_view(s, "p1")["here"] == {"place": "Ikebe Low", "mood": "wary", "mark": "smashed noodle stall"}


def test_old_saves_load_without_places(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data.pop("places")
    path.write_text(json.dumps(data))
    assert store.load("old").places == {}


def test_a_long_fight_locks_down_once_and_heat_cools_while_you_stay():
    s = _session()
    s.location = "Kuroshio Docks"
    s.in_combat = True
    for _ in range(6):
        director.tick(s, "p1", _turn(s))
    assert sum(e.startswith("Ōgane Heavy sweeps") for e in s.pending_world_events) == 1
    s.in_combat = False
    for _ in range(25):
        director.tick(s, "p1", _turn(s))
    assert _here(s)["heat"] < 9 - 4


def test_a_mark_you_stay_with_is_kept():
    s = _session()
    s.location = "Ikebe Low"
    places.mark(s, "smashed noodle stall")
    for _ in range(40):
        director.tick(s, "p1", _turn(s))
    assert _here(s)["marks"][0]["permanent"]


def test_one_place_however_it_is_written():
    s = _session()
    s.location = "Mama Sato's izakaya"
    first = places.key(s)
    s.location = "the izakaya"
    assert places.key(s) == first
