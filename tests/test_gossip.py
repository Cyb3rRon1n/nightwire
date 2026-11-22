import json
import random

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import director, gossip, people
from narrator.referee import apply_verdict, ground
from server.narration import _build_messages
from server.views import build_view
from tests.test_referee import _session


def _advance(s: Session, n: int) -> None:
    for _ in range(n):
        s.log.append("p1: I walk.")
        gossip.tick(s)


def _docks() -> Session:
    s = _session()
    s.location = "Kuroshio Docks"
    people.meet(s, "dockworker with a burned hand", "Rook punched him")
    for who in ("crane operator", "net mender", "fish seller"):
        people.meet(s, who, "watched Rook")
    s.present = ["Tetsu"]
    return s


def test_a_deed_is_seen_by_whoever_is_there():
    s = _docks()
    gossip.record(s, "Rook punched Tetsu", False)
    assert s.deeds[0]["knows"] == {"Tetsu": {"s": 3, "text": "Rook punched Tetsu", "seen": True}}
    s.present = []
    gossip.record(s, "Rook kicked a can", False)
    assert len(s.deeds) == 1  # nobody there, nobody to tell


def test_word_spreads_two_hops_then_stops(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.99)  # no exaggeration
    s = _docks()
    gossip.record(s, "Rook punched Tetsu", False)
    _advance(s, 5)
    strengths = sorted(k["s"] for k in s.deeds[0]["knows"].values())
    assert strengths == [2, 3]
    _advance(s, 25)
    assert min(k["s"] for k in s.deeds[0]["knows"].values()) >= 0
    assert all(not k["seen"] for n, k in s.deeds[0]["knows"].items() if n != "Tetsu")


def test_exaggeration_follows_the_owner_table():
    assert gossip.exaggerate("Rook punched Tetsu") == "Rook put Tetsu in the clinic"
    assert gossip.exaggerate("Rook started a fight at Ikebe Low") == "Rook started a brawl at Ikebe Low"
    assert gossip.exaggerate("Rook broke their word to Mama Sato") == "Rook can't be trusted - ask Mama Sato"
    assert gossip.exaggerate("Rook bought noodles") == "Rook bought noodles"


def test_old_news_fades_away():
    s = _docks()
    gossip.record(s, "Rook punched Tetsu", False)
    s.deeds[0]["knows"]["Tetsu"]["s"] = 1
    s.log += ["p1: I walk."] * 29
    _advance(s, 1)
    assert s.deeds == []


def test_amends_clear_the_bad_word_that_person_heard():
    s = _docks()
    gossip.record(s, "Rook punched Tetsu", False)
    gossip.record(s, "Rook helped Tetsu at a cost", True)
    gossip.amends(s, "Tetsu")
    assert [d["what"] for d in s.deeds] == ["Rook helped Tetsu at a cost"]


def test_a_walk_on_deed_from_the_referee_is_recorded_and_the_narrator_hedges_heard_news():
    s = _session()
    s.location = "Kuroshio Docks"
    apply_verdict(s, "p1", ground(s, {"new_person": "dockworker with a burned hand: Rook punched him"},
                                  "I punch the guy.", "The dockworker staggers back."))
    assert s.deeds[0]["what"] == "Rook punched him" and not s.deeds[0]["good"]
    s.deeds[0]["knows"]["Old Hara"] = {"s": 2, "text": "Rook put him in the clinic", "seen": False,
                                       "exaggerated": True}
    s.present = ["Old Hara"]
    s.log = ["p1: I visit Hara."]
    prompt = _build_messages(s, "I visit Hara.", 8192)[-1]["content"]
    assert "Old Hara has heard (second-hand, maybe exaggerated): Rook put him in the clinic." in prompt
    assert build_view(s, "p1")["street"] == [{"district": "Kuroshio Docks", "good": None, "bad": "Rook punched him"}]


def test_a_fight_turn_is_a_deed_once():
    s = _docks()
    for _ in range(3):
        s.log += ["p1: I swing.", '[roll: {"skill": "melee", "outcome": "failure"}]']
        director.tick(s, "p1", s.characters["p1"].health)
    assert [d["what"] for d in s.deeds] == ["Rook started a fight at Kuroshio Docks"]


def test_old_saves_load_without_deeds(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data.pop("deeds")
    path.write_text(json.dumps(data))
    assert store.load("old").deeds == []
