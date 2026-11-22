import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import director, people
from narrator.cast import present_line
from narrator.referee import apply_verdict, ground
from server.views import build_view
from tests.test_referee import _session

ACTION = "I punch the guy who bumps into me."
SCENE = "The dockworker with the burned hand staggers back, clutching his jaw."


def _met(s: Session, answer: str, action: str = ACTION, scene: str = SCENE) -> None:
    apply_verdict(s, "p1", ground(s, {"new_person": answer}, action, scene))


def test_a_grounded_walk_on_gets_a_district_name_joins_the_scene_and_remembers():
    s = _session()
    s.location = "Kuroshio Docks"
    _met(s, "dockworker with a burned hand: Rook punched him")
    assert list(s.people) == ["Tetsu"]
    assert s.people["Tetsu"]["weight"] == 1
    assert "Tetsu" in s.present
    assert "Tetsu (dockworker with a burned hand)" in present_line(s)
    assert s.npc_memory["Tetsu"][-1]["text"] == "Rook punched him"


def test_an_invented_person_is_ignored():
    s = _session()
    s.location = "Kuroshio Docks"
    _met(s, "a priest in white robes: blessed Rook")
    _met(s, "no colon here")
    assert s.people == {}


def test_the_same_person_again_matters_more_instead_of_doubling():
    s = _session()
    s.location = "Kuroshio Docks"
    _met(s, "dockworker with a burned hand: Rook punched him")
    _met(s, "burned dockworker: Rook paid him back", "I find the dockworker and pay him.", SCENE)
    assert list(s.people) == ["Tetsu"] and s.people["Tetsu"]["weight"] == 2


WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo",
         "lima", "mike"]


def test_a_full_roster_drops_the_weakest_into_the_journal():
    s = _session()
    s.location = "Ikebe Low"
    for i in range(people.MAX_PEOPLE + 1):
        people.meet(s, f"{WORDS[i]}x", "sold Rook noodles")
        s.log.append("p1: I walk.")
    assert len(s.people) == people.MAX_PEOPLE
    assert s.journal[-1]["kind"] == "lost touch"


def test_names_run_out_gracefully():
    s = _session()
    s.location = "Ikebe Low"
    for i in range(40):
        people.meet(s, f"stranger{i}", "met Rook")
    assert len(s.people) == people.MAX_PEOPLE


def test_a_comeback_event_brings_someone_back_by_weight_with_a_lead():
    s = _session()
    s.location = "Kuroshio Docks"
    people.meet(s, "dockworker with a burned hand", "Rook punched him")
    s.present = []
    event = director.pick(s, "p1")
    assert event["id"] == "comeback"
    director.fire(s, event)
    assert s.pending_world_events == [
        "Tetsu, the dockworker with a burned hand, turns up again - they haven't forgotten: Rook punched him."]
    assert "See what Tetsu wants" in s.active_objectives and "Tetsu" in s.present
    assert people.comeback(s) is None  # not again within 20 turns


def test_people_show_in_the_view_and_old_saves_load(tmp_path):
    s = _session()
    s.location = "Kuroshio Docks"
    people.meet(s, "dockworker with a burned hand", "Rook punched him")
    assert build_view(s, "p1")["people"][0]["name"] == "Tetsu"
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data.pop("people")
    path.write_text(json.dumps(data))
    assert store.load("old").people == {}
