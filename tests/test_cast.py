from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.cast import note, present_line, refresh


def test_a_move_leaves_everyone_behind_but_the_keeper_and_who_the_action_names():
    # Soak 2026-11-19 turn 28: Mama Sato spoke to Rin as she woke up, far from the izakaya.
    s = Session(session_id="s", location="Ikebe Low", cast_location="Ikebe Low", present=["Wataru Ono"])
    s.location = "Mama Sato's izakaya"
    refresh(s, "I walk to the izakaya with Old Hara.")
    assert s.present == ["Mama Sato", "Old Hara"] and s.cast_location == "Mama Sato's izakaya"
    s.location = "Kuroshio Docks"
    refresh(s, "I head to the docks.")
    assert s.present == []


def test_no_move_keeps_the_cast():
    s = Session(session_id="s", location="Ikebe Low", cast_location="Ikebe Low", present=["Wataru Ono"])
    refresh(s, "I look around.")
    assert s.present == ["Wataru Ono"]


def test_who_speaks_or_is_named_in_the_story_joins():
    s = Session(session_id="s", location="Ikebe Low", cast_location="Ikebe Low")
    note(s, [("Hachi", "Hey."), ("narrator", "Old Hara waves from the curtain."), ("a dockworker", "Move.")])
    assert s.present == ["Hachi", "Old Hara"]


def test_the_line_tells_the_narrator_who_is_here():
    assert present_line(Session(session_id="s", present=["Mama Sato"])) == \
        "Present: Mama Sato. Anyone else must arrive on screen first."
    assert present_line(Session(session_id="s")) == \
        "Present: no named characters. Anyone else must arrive on screen first."


def test_the_cast_is_saved(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="s", present=["Hachi"], cast_location="Kuroshio Docks"))
    loaded = store.load("s")
    assert loaded.present == ["Hachi"] and loaded.cast_location == "Kuroshio Docks"
