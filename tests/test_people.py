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
    assert people.comeback(s) is None  # standing right here, and only just met
    s.present = []
    s.log += ["p1: I walk."] * people.RETURN_GAP
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


def test_named_people_and_generic_words_do_not_make_or_merge_walk_ons():
    s = _session()
    s.location = "Ikebe Low"
    _met(s, "Old Hara with a wrench: helped Rook", "I ask Old Hara for help.", "Old Hara hands Rook a wrench.")
    assert s.people == {}
    people.meet(s, "ticket vendor", "sold Rook a pass")
    people.meet(s, "noodle vendor with a limp", "fed Rook")
    assert len(s.people) == 2


def test_a_name_that_is_also_a_word_only_counts_capitalised():
    from narrator.cast import _named
    s = _session()
    s.people["Shin"] = {"who": "x", "what": "y", "district": None, "place": None, "turn": 0, "weight": 1,
                        "returned": None}
    assert _named("She kicks him in the shin.", s) == []
    assert _named("Shin waves.", s) == ["Shin"]


def test_an_unnamed_speaker_is_promoted_when_the_referee_names_no_one():
    # Soak 2026-11-22: "man in black duster" grabbed Rin and spoke three turns running; new_person stayed empty.
    s = _session()
    s.location = "Ikebe Low"
    scene = "A hand grabs your wrist.\nman in black duster: You don't punch me, kid."
    _met(s, "", ACTION, scene)
    (name,) = s.people
    assert s.people[name]["who"] == "man in black duster"
    assert s.people[name]["what"] == f'the player did this: "{ACTION.rstrip(".")}"'
    _met(s, "", "I apologise and help him up.", "man in black duster: You think you're clever, kid.")
    assert list(s.people) == [name] and s.people[name]["weight"] == 2


def test_a_named_speaker_is_not_promoted():
    s = _session()
    s.location = "Ikebe Low"
    _met(s, "", ACTION, "Mama Sato: Sit down, child.")
    assert s.people == {}


def test_a_bare_description_from_the_referee_takes_the_action_as_what_happened():
    # Soak 2026-11-22: the referee fills a bare "enforcer" where it left "who: what" empty.
    s = _session()
    s.location = "Ikebe Low"
    _met(s, "enforcer", ACTION, "The enforcer catches your fist mid-air.")
    (name,) = s.people
    assert (s.people[name]["who"], s.people[name]["what"]) == ("enforcer", f'the player did this: "{ACTION.rstrip(".")}"')


def test_a_plain_man_counts_when_his_details_are_in_the_scene():
    # Soak 2026-11-22 turn 25: "man with sake breath" was dropped because "man" is too plain a word.
    s = _session()
    s.location = "Ikebe Low"
    _met(s, "man with sake breath", ACTION, "A man bumps into you, his sake breath hot on your face.")
    assert [p["who"] for p in s.people.values()] == ["man with sake breath"]
    _met(s, "man with a scar", ACTION, "A man bumps into you.")
    assert len(s.people) == 1


def test_a_named_answer_is_dropped_quietly():
    s = _session()
    s.location = "Ikebe Low"
    _met(s, "Mama Sato", ACTION, "Mama Sato: Sit, child.")
    assert s.people == {} and not any("new_person" in line for line in s.log)


def test_voices_shadows_and_groups_are_not_people():
    s = _session()
    s.location = "Ikebe Low"
    _met(s, "A voice calls out from the shadows", "I look around.", "A voice calls out from the shadows.")
    _met(s, "security enforcers", "I take the train.", "Security enforcers watch the platform.")
    _met(s, "", "I look around.", "kuze boys: Move along.")
    assert s.people == {}
    _met(s, "dockworker with a burned hand", ACTION, "The dockworker with a burned hand staggers.")
    assert len(s.people) == 1  # a singular "hand" after "with" doesn't trip the plural rule


def test_a_walk_on_the_action_never_dealt_with_is_not_promoted():
    # Soak 2026-11-22: "noren curtain" became Goro on the arrival turn.
    s = _session()
    _met(s, "noren curtain", "I step off the Ring Line at Ikebe Low and look around.",
         "A noren curtain sways in the breeze, revealing a small clinic.")
    assert not s.people and any("not someone the action dealt with" in l for l in s.log)


def test_him_is_the_walk_on_already_here_even_described_differently():
    # Soak 2026-11-24: Daisuke ("man with a blade") was punched, then "I apologise and help him up" made "Fumi = man
    # with sharp eyes", so neither ever came back.
    s = _session()
    s.location = "Kuroshio Docks"
    _met(s, "dockworker with a burned hand: Rook punched him")
    _met(s, "man with sharp eyes: Rook helped him up", "I apologise and help him up.",
         "The man with sharp eyes takes your hand.")
    assert list(s.people) == ["Tetsu"] and s.people["Tetsu"]["weight"] == 2
