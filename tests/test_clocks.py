import json

import pytest

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import clocks
from tests.test_referee import _session

CRANE = "Find out who jammed the crane at Kuroshio Docks before Ōgane does"
MELEE = [{"skill": "melee", "outcome": "clean_success"}]


def _at(place: str, **filled) -> Session:
    s = _session()
    s.location = place
    s.log.append("p1: I look around.")  # one player turn, so "this turn" has a number
    clocks.tick(s, [], False)  # first sight of every clock: no night counted
    for cid, n in filled.items():
        s.clocks[cid.replace("_", "-")]["filled"] = n
    return s


def _turn(s: Session, rolls=(), heat_rose=False, done=()) -> None:
    s.log.append("p1: I keep going.")
    from narrator.cast import _player_turns
    s.journal += [{"text": t, "kind": "done", "turn": _player_turns(s)} for t in done]
    clocks.tick(s, list(rolls), heat_rose)


def _filled(s: Session, cid: str) -> int:
    return s.clocks[cid]["filled"]


def test_world_file_loads():
    assert {c["id"] for c in clocks.defs()} == {"ogane-docks", "container", "kuze-ikebe"}
    assert sum(bool(c["shown"]) for c in clocks.defs()) <= 2


GOOD = {"id": "x", "name": "X", "size": 4, "where": ["Ikebe Low"], "ticks": ["night"], "full": "f", "lead": "l"}


@pytest.mark.parametrize("bad", [{"size": 5}, {"ticks": ["riot"]}, {"where": ["Atlantis"]},
                                 {"portents": {"6": "too late"}}, {"full": ""}])
def test_validate_rejects(bad):
    clocks.validate([GOOD])
    with pytest.raises(ValueError):
        clocks.validate([{**GOOD, **bad}])


def test_fight_in_district_moves_one():
    s = _at("Kuroshio Docks")
    _turn(s, MELEE, heat_rose=True)
    assert (_filled(s, "ogane-docks"), _filled(s, "kuze-ikebe")) == (1, 0)


def test_fight_and_new_night_still_one():
    s = _at("Kuroshio Docks")
    s.night += 1
    _turn(s, MELEE, heat_rose=True)
    assert (_filled(s, "ogane-docks"), _filled(s, "container")) == (1, 1)


def test_first_tick_counts_no_night():
    s = _session()
    s.night = 3
    s.location = "Kuroshio Docks"
    s.log.append("p1: I wake.")
    clocks.tick(s, [], False)
    assert _filled(s, "container") == 0


def test_portent_queued_on_stage():
    s = _at("Kuroshio Docks", ogane_docks=1)
    _turn(s, MELEE)
    assert _filled(s, "ogane-docks") == 2
    assert any("drones" in e for e in s.pending_world_events)
    assert "[clock: ogane-docks 2/6]" in s.log


def test_ease_then_rise_requeues_portent():
    s = _at("Kuroshio Docks", ogane_docks=2)
    _turn(s, done=[CRANE])
    assert _filled(s, "ogane-docks") == 1
    s.pending_world_events.clear()
    _turn(s, MELEE)
    assert _filled(s, "ogane-docks") == 2 and any("drones" in e for e in s.pending_world_events)


def test_kuze_eases_on_any_ikebe_lead():
    s = _at("Kuroshio Docks", kuze_ikebe=3)
    _turn(s, done=["Ask at the Low-city shrine who cut Ikebe Low's power"])
    assert _filled(s, "kuze-ikebe") == 2


def test_ogane_ignores_other_docks_leads():
    s = _at("Kuroshio Docks", ogane_docks=3)
    _turn(s, done=["Investigate the sealed container at Kuroshio Docks"])
    assert _filled(s, "ogane-docks") == 3


def test_full_fires_lead_and_rests():
    s = _at("Ikebe Low", container=3)
    s.night += 1
    _turn(s)
    assert _filled(s, "container") == 0
    assert any("ships out" in e for e in s.pending_world_events)
    assert "Find out where the no-manifest container went" in s.active_objectives
    assert "[clock: container full]" in s.log
    s.night += 1
    _turn(s)
    assert _filled(s, "container") == 0


def test_rest_ignores_eases_too():
    s = _at("Ikebe Low", kuze_ikebe=5)
    _turn(s, [{"skill": "stealth", "outcome": "failure"}])
    assert _filled(s, "kuze-ikebe") == 0
    _turn(s, done=["Find out who in Ikebe Low is paying the Kuze-gumi"])
    assert _filled(s, "kuze-ikebe") == 0


def test_never_below_zero():
    s = _at("Ikebe Low")
    _turn(s, done=["Ask at the Low-city shrine who cut Ikebe Low's power"])
    assert _filled(s, "kuze-ikebe") == 0


def test_line_and_view():
    s = _at("Ikebe Low", kuze_ikebe=4)
    assert clocks.line(s) == "Pressure: Kuze-gumi squeeze on Ikebe Low 4/6."
    d = _at("Kuroshio Docks", container=2)
    assert clocks.line(d) == ""
    assert [v["name"] for v in clocks.view(d)] == ["Ōgane crackdown on the Docks", "Kuze-gumi squeeze on Ikebe Low"]


def test_old_save_loads(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="old"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data.pop("clocks")
    path.write_text(json.dumps(data))
    assert store.load("old").clocks == {}
