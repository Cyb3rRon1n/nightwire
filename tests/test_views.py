from engine.character import CharacterSheet
from engine.session import Session
from server.views import build_view


def _character(player_id: str, name: str) -> CharacterSheet:
    return CharacterSheet(
        player_id=player_id,
        name=name,
        role="solo",
        lifepath="streetkid",
        attributes={"body": 14},
        health=7,
        max_health=10,
        armor=2,
        conditions=["bleeding"],
        inventory=["stim pack"],
    )


def test_viewer_sees_their_own_full_sheet():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")

    view = build_view(session, "p1")

    assert view["characters"]["p1"] == {
        "player_id": "p1",
        "name": "Rook",
        "role": "solo",
        "lifepath": "streetkid",
        "attributes": {"body": 14},
        "health": 7,
        "max_health": 10,
        "armor": 2,
        "conditions": ["bleeding"],
        "inventory": ["stim pack"],
        "portrait_path": None,
        "skills": {},
        "unspent_skill_points": 0,
        "unspent_attribute_points": 0,
        "humanity": 100,
        "chrome": [],
        "installments_owed": 0,
        "slipping_warned": False,
        "gone_too_far": False,
    }


def test_viewer_sees_a_redacted_view_of_other_players():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Ghost")

    view = build_view(session, "p1")

    assert view["characters"]["p2"] == {
        "name": "Ghost",
        "role": "solo",
        "health": 7,
        "max_health": 10,
        "armor": 2,
        "conditions": ["bleeding"],
    }
    assert "inventory" not in view["characters"]["p2"]
    assert "attributes" not in view["characters"]["p2"]
    assert "player_id" not in view["characters"]["p2"]


def test_view_includes_shared_session_state():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Ghost")
    session.turn_order = ["p2", "p1"]
    session.in_combat = True
    session.current_turn_index = 0
    session.log = ["Rook draws a pistol."]

    view = build_view(session, "p1")

    assert view["session_id"] == "s1"
    assert view["in_combat"] is True
    assert view["current_turn"] == "p2"
    assert view["is_your_turn"] is False
    assert view["log"] == ["Rook draws a pistol."]


def test_is_your_turn_true_outside_combat():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")

    view = build_view(session, "p1")

    assert view["current_turn"] is None
    assert view["is_your_turn"] is True


def test_view_includes_world_state():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.location = "Watson district"
    session.scene_mood = "tense"
    session.active_objectives = ["find the fixer"]

    view = build_view(session, "p1")

    assert view["location"] == "Watson district"
    assert view["scene_mood"] == "tense"
    assert view["active_objectives"] == ["find the fixer"]


def test_view_has_a_state_type_discriminator():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")

    view = build_view(session, "p1")

    assert view["type"] == "state"


def test_view_exposes_pending_rolls_to_every_viewer():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Vex")
    session.pending_rolls["p1"] = {"player_id": "p1", "skill": "stealth", "dc": 16}

    expected = {"p1": {"player_id": "p1", "skill": "stealth", "dc": 16, "overclocks": []}}
    assert build_view(session, "p1")["pending_rolls"] == expected
    assert build_view(session, "p2")["pending_rolls"] == expected


def test_overclocks_on_a_pending_roll_are_only_filled_for_its_owner():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Vex")
    session.characters["p1"].chrome = ["kagerou"]
    session.pending_rolls["p1"] = {"player_id": "p1", "skill": "stealth", "dc": 12}
    assert [o["id"] for o in build_view(session, "p1")["pending_rolls"]["p1"]["overclocks"]] == ["kagerou"]
    assert build_view(session, "p2")["pending_rolls"]["p1"]["overclocks"] == []


def test_view_exposes_pending_chrome_offers():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Vex")
    session.pending_chrome_offers["p1"] = "kagerou"
    assert build_view(session, "p1")["pending_chrome_offers"] == {"p1": "kagerou"}
    assert build_view(session, "p2")["pending_chrome_offers"] == {}
