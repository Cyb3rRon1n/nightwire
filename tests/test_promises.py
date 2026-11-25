import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import promises
from narrator.referee import apply_verdict, build_questions, ground
from server.narration import _build_messages
from server.views import build_view
from tests.test_referee import _session

ACTION = "I promise Mama Sato I'll find her nephew Kenta."
SCENE = 'Mama Sato: "Bring Kenta home, child. His mother is sick with worry about her nephew."'


def _turns(s: Session, n: int) -> None:
    s.log += ["p1: I wait."] * n


def test_a_promise_in_the_scene_is_recorded_once():
    s = _session()
    verdict = ground(s, {"promise_made": "Mama Sato: find her nephew Kenta"}, ACTION, SCENE)
    apply_verdict(s, "p1", verdict)
    apply_verdict(s, "p1", verdict)
    assert s.promises == [{"who": "Mama Sato", "what": "find her nephew Kenta", "turn": 0, "called_in": False}]


def test_an_invented_promise_is_ignored():
    s = _session()
    for answer in ("Old Hara: fix the generator", "Mama Sato: steal the Hoshikawa vault keys", "no colon here"):
        apply_verdict(s, "p1", ground(s, {"promise_made": answer}, ACTION, SCENE))
    assert s.promises == []


def test_open_promises_ask_about_keeping_them_even_without_contacts():
    s = _session()
    assert "kept_promise_to" not in build_questions(s, "p1")
    promises.record(s, "Mama Sato", "find Kenta")
    assert {"kept_promise_to", "broke_promise_to"} <= set(build_questions(s, "p1"))


def test_keeping_and_breaking_close_the_promise_and_go_in_the_journal():
    s = _session()
    promises.record(s, "Mama Sato", "find Kenta")
    promises.record(s, "Old Hara", "pay him back")
    apply_verdict(s, "p1", {"kept_promise_to": "Sato", "broke_promise_to": "Old Hara"})
    assert s.promises == []
    assert [(j["text"], j["kind"]) for j in s.journal] == [("Mama Sato: find Kenta", "kept"),
                                                          ("Old Hara: pay him back", "broken")]
    assert s.pending_world_events == ["Old Hara remembers Rook broke their word: pay him back."]


def test_the_narrator_is_reminded_when_the_person_is_here_or_the_promise_is_old():
    s = _session()
    promises.record(s, "Mama Sato", "find Kenta")
    assert promises.business_line(s) == ""
    s.present = ["Mama Sato"]
    _turns(s, 3)
    line = "Unfinished business: Mama Sato: find Kenta (3 turns ago)."
    assert promises.business_line(s) == line and line in _build_messages(s, "I sit.", 8192)[0]["content"]
    s.present = []
    _turns(s, 5)
    assert promises.business_line(s).startswith("Unfinished business: Mama Sato")


def test_an_old_promise_is_called_in_once():
    s = _session()
    promises.record(s, "Mama Sato", "find Kenta")
    _turns(s, 15)
    promises.call_in(s)
    assert s.pending_world_events == []
    _turns(s, 1)
    promises.call_in(s)
    promises.call_in(s)
    assert s.pending_world_events == ["Mama Sato hasn't forgotten: find Kenta."]
    assert s.journal[-1]["kind"] == "called in" and s.promises  # still open


def test_six_open_at_most_and_objectives_pushed_off_are_set_aside():
    s = _session()
    for i in range(8):
        promises.record(s, f"P{i}", "x")
    assert [p["who"] for p in s.promises] == [f"P{i}" for i in range(2, 8)]
    assert [j["text"] for j in s.journal] == ["P0: x", "P1: x"]
    s.journal = []
    s.active_objectives = [f"o{i}" for i in range(5)]
    apply_verdict(s, "p1", {"new_lead": "o5", "objective_done": "o2"})
    assert s.active_objectives == ["o0", "o1", "o3", "o4", "o5"]
    assert [(j["text"], j["kind"]) for j in s.journal] == [("o2", "done")]
    apply_verdict(s, "p1", {"new_lead": "o6"})
    apply_verdict(s, "p1", {"new_lead": "o7"})
    assert s.active_objectives == ["o3", "o4", "o5", "o6", "o7"]
    assert [(j["text"], j["kind"]) for j in s.journal][1:] == [("o0", "set aside"), ("o1", "set aside")]


def test_the_player_sees_promises_and_the_journal_and_old_saves_load(tmp_path):
    s = _session()
    promises.record(s, "Mama Sato", "find Kenta")
    promises.note(s, "Pick up Jun's case", "done")
    _turns(s, 2)
    view = build_view(s, "p1")
    assert view["promises"] == [{"who": "Mama Sato", "what": "find Kenta", "ago": 2}]
    assert view["journal"][0]["text"] == "Pick up Jun's case" and view["journal"][0]["ago"] == 2
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    del data["promises"], data["journal"]
    path.write_text(json.dumps(data))
    loaded = store.load("old")
    assert loaded.promises == [] and loaded.journal == []


def test_review_fixes_whole_words_ambiguous_names_and_long_promises():
    # Review 2026-11-22: "Ken" matched "token"; "Mama" closed the wrong promise; "what" was cut mid-word.
    s = _session()
    apply_verdict(s, "p1", ground(s, {"promise_made": "Ken: steal the vault keys"}, "I hold a token.",
                                  "The vault keys are behind the counter."))
    assert s.promises == []
    promises.record(s, "Mama Sato", "find Kenta")
    promises.record(s, "Mama Kobayashi", "fix the radio")
    promises.close(s, "Mama", True, "Rook")
    assert len(s.promises) == 2
    promises.close(s, "Kobayashi", True, "Rook")
    assert [p["who"] for p in s.promises] == ["Mama Sato"]
    who, what = promises.split("Mama Sato: bring her nephew Kenta home before the night market closes on the "
                               "longest night of the whole cold year")
    assert len(what) <= 80 and what.endswith(("night", "the", "whole", "of", "year", "cold", "longest"))
    for i in range(6):
        promises.record(s, f"P{i}", "x")
    assert s.journal[-1] == {"text": "Mama Sato: find Kenta", "kind": "set aside", "turn": 0}


def test_a_promise_in_the_players_own_words_is_kept_when_the_referee_picks_the_wrong_one():
    # Soak 2026-11-24 (17) turn 15: "I thank him and promise to bring him tea tomorrow." The referee answered with
    # Hara's own "I'll fix it", which was rightly too vague, and the tea promise was lost.
    s = _session()
    s.present = ["Old Hara"]
    action = "I thank him and promise to bring him tea tomorrow."
    scene = "Old Hara: I'll fix it. But you'll owe me more than tea."
    apply_verdict(s, "p1", ground(s, {"promise_made": "Old Hara: fix it"}, action, scene))
    assert [(p["who"], p["what"]) for p in s.promises] == [("Old Hara", "bring him tea tomorrow")]


def test_a_promise_in_the_action_needs_exactly_one_named_person_here():
    s = _session()
    action = "I promise to bring tea tomorrow."
    for present in ([], ["Old Hara", "Mama Sato"]):
        s.present = present
        apply_verdict(s, "p1", ground(s, {"promise_made": ""}, action, "The bulb flickers."))
    assert s.promises == []


def test_the_action_backstop_only_takes_the_players_own_promise():
    # Review 2026-11-24: negations, other people's promises and "promising" made promises; odd spacing crashed.
    s = _session()
    s.present = ["Old Hara"]
    for action in ("I follow the promising lead to the docks.", "I make no promises to anyone.",
                   "Hara promised me he'd fix it, so I wait.", "I can't promise that he'll live.",
                   "I ask her to promise she'll stay.", "I promise    ."):
        apply_verdict(s, "p1", ground(s, {"promise_made": ""}, action, "The bulb flickers."))
    assert s.promises == []


def test_the_action_backstop_cleans_up_the_words_and_takes_a_named_person():
    s = _session()
    s.present = ["Old Hara", "Mama Sato"]
    apply_verdict(s, "p1", ground(s, {"promise_made": ""}, "I promise Mama Sato I'll find Kenta.", "She nods."))
    s.present = ["Old Hara"]
    apply_verdict(s, "p1", ground(s, {"promise_made": ""}, "I promised her I'd bring tea.", "He nods."))
    apply_verdict(s, "p1", ground(s, {"promise_made": ""}, "I promise you I'll be back.", "He nods."))
    assert [(p["who"], p["what"]) for p in s.promises] == [
        ("Mama Sato", "find Kenta"), ("Old Hara", "bring tea"), ("Old Hara", "be back")]


def test_i_promise_him_with_a_walk_on_here_records_nothing():
    s = _session()
    s.present, s.people["Tomoe"] = ["Old Hara", "Tomoe"], {"who": "kuze-gumi"}
    apply_verdict(s, "p1", ground(s, {"promise_made": ""}, "I promise him I'll come back.", "He nods."))
    assert s.promises == []
