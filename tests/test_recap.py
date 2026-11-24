import json

from engine.character import CharacterSheet
from narrator import places, recap
from tests.test_referee import _session


def _turn(s, action, place, *lines, n=None):
    s.log.append(f"p1: {action}")
    s.log.extend(lines)
    s.trail.append([sum(l.startswith("p1: ") for l in s.log), place])


def _roll(outcome):
    return f"[roll: {json.dumps({'outcome': outcome, 'skill': 'melee'})}]"


def test_a_short_night_shows_every_turn():
    s = _session()
    _turn(s, "I look around.", "Ikebe Low", "Lanterns sway in the rain.")
    _turn(s, "I walk on.", "Ikebe Low", "The alley narrows.")
    ps = recap.panels(s)
    assert [p["n"] for p in ps] == [1, 2]
    assert ps[0]["text"] == "Lanterns sway in the rain." and ps[0]["action"] == "Rook: I look around."


def test_no_turns_no_panels():
    assert recap.panels(_session()) == []


def test_first_last_and_each_new_district_are_kept_and_at_most_twelve():
    s = _session()
    for i in range(30):
        place = "Kuroshio Docks" if i == 14 else "Ikebe Low"
        _turn(s, f"I do thing {i}.", place, f"Thing {i} happens.", *([_roll("failure")] if i % 2 else []))
    ns = [p["n"] for p in recap.panels(s)]
    assert ns[0] == 1 and ns[-1] == 30 and 15 in ns and len(ns) <= 12


def test_a_busy_scene_gets_its_share_and_a_one_place_night_fills_the_sheet():
    s = _session()
    for i in range(20):
        _turn(s, f"I fight {i}.", "Ikebe Low", f"Blow {i}.", _roll("clean_success"))
    assert len(recap.panels(s)) == 12
    s = _session()
    for i in range(24):
        _turn(s, f"I fight {i}.", "Ikebe Low" if i < 4 else "Kuroshio Docks", f"Blow {i}.", _roll("clean_success"))
    ikebe = [p for p in recap.panels(s) if p["place"] == "Ikebe Low"]
    assert len(ikebe) == 3  # 4 of 24 turns: its share is 2, so the floor of 3


def test_speech_panel_takes_the_shortest_fitting_line_and_portrait():
    s = _session()
    _turn(s, "I sit at the bar.", "Mama Sato's izakaya", "The bar is warm.",
          "Mama Sato: Sit down, child, before you fall down.", "Mama Sato: Eat.",
          "Mama Sato: You look like the rain chewed you up and spat you out again tonight.")
    p = recap.panels(s)[0]
    assert (p["speaker"], p["text"]) == ("Mama Sato", "Sit down, child, before you fall down.")
    assert p["portrait"] == "character-art/mama-sato.jpg"


def test_no_bracket_text_reaches_a_panel_and_the_players_own_voice_is_not_speech():
    s = _session()
    _turn(s, "I wait.", "Ikebe Low", "[director: ikebe-blackout]", "Rook: I am not talking to an NPC here.",
          "The lights die.", "[pressure: kuze-ikebe 2/6]")
    p = recap.panels(s)[0]
    assert p["speaker"] is None and p["text"] == "The lights die."
    assert not any("[" in str(v) for v in p.values())


def test_a_roll_setup_and_its_resolution_are_one_turn():
    s = _session()
    s.log += ["p1: I jump the gap.", "[roll pending: {}]", "You size up the gap.", _roll("complication"),
              "You land hard."]
    (t,) = recap.turns(s)
    assert recap.score(t) == 1 and t["lines"] == ["You size up the gap.", "You land hard."]


def test_party_names_and_old_saves_without_a_trail():
    s = _session()
    s.characters["p2"] = CharacterSheet(player_id="p2", name="Rin", role="netrunner", lifepath="streetkid")
    s.location = "Ikebe Low"
    s.log += ["p1: I keep watch.", "Rain.", "p2: I jack in.", "Static."]
    ps = recap.panels(s)
    assert [p["action"] for p in ps] == ["Rook: I keep watch.", "Rin: I jack in."]
    assert {p["place"] for p in ps} == {"Ikebe Low"}


def test_art_prefers_the_turns_scene_image_then_place_art():
    s = _session()
    _turn(s, "I look.", "Ikebe Low", "Rain.", "[image: scenes/abc.png]")
    _turn(s, "I go.", "Kuroshio Docks", "Cranes.")
    a, b = recap.panels(s)
    assert (a["art"], b["art"]) == ("scenes/abc.png", "place-art/kuroshio-docks.jpg")


def test_scores_and_the_new_log_lines():
    s = _session()
    s.location = "Ikebe Low"
    places.mark(s, "a cracked window")
    assert s.log[-1] == "[mark: a cracked window]"
    t = {"notes": ["[promise: Old Hara: tea]", "[rated: like]", "[director: breather]", "[mark: x]", _roll("failure")]}
    assert recap.score(t) == 3 + 3 + 0 + 1 + 2


def test_facts():
    s = _session()
    s.people = {"Tomoe": {"who": "man with broken wrist"}}
    s.promises = [{"who": "Old Hara", "what": "bring tea"}]
    s.active_objectives = ["Find Jun"]
    f = recap.facts(s)
    assert f["people"] == ["Tomoe, man with broken wrist"] and f["promises_open"] == ["Old Hara: bring tea"]
    assert f["leads"] == ["Find Jun"]
