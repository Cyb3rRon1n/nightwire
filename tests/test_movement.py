import pytest

from narrator.movement import destination, known_place


@pytest.mark.parametrize("action, place", [
    ("I head to Mama Sato's izakaya.", "Mama Sato's izakaya"),
    ("I leave and walk to Old Hara's clinic.", "Old Hara's clinic"),
    ("I go to the Kuroshio Docks to find work.", "Kuroshio Docks"),
    ("I take the Ring Line to Tenjō Heights.", "Tenjō Heights"),
    ("I head back toward Ikebe Low.", "Ikebe Low"),
    ("i walk over to the izakaya", "Mama Sato's izakaya"),
    ("I ride out to the junkyard", "Junkyard workshop"),
    ("I enter the precinct.", "Ōgane precinct"),
    ("I follow Mama Sato into her izakaya and sit at the counter.", "Mama Sato's izakaya"),
])
def test_moves_to_a_known_place(action, place):
    assert destination(action) == place


@pytest.mark.parametrize("action", [
    "I ask Mama Sato what's good tonight.",       # names a place, no movement
    "I tell him I saw Hara at the docks.",         # talk about a place
    "I go home to my room and sleep.",             # unknown place: the referee decides
    "I walk over and sit at the collector's table.",
])
def test_no_move(action):
    assert destination(action) is None


def test_known_place_picks_the_longest_name():
    assert known_place("Ikebe Low - Old Hara's clinic") == "Old Hara's clinic"
    assert known_place("the alleyway behind Mama Sato's izakaya") == "Mama Sato's izakaya"
    assert known_place("tenjo") == "Tenjō Heights"
    assert known_place("a cramped bathroom") is None


def test_an_everyday_loop_in_the_prose_is_not_the_loop():
    # Soak 2026-11-18: a train scene drifted to The Loop; the Ring Line's card calls it "the commuter loop".
    from narrator.movement import places_in
    assert places_in("The train rounds the commuter loop.") == set()
    assert known_place("a loop of cable") is None
    assert known_place("Kaminari Run bikes race the Loop.") == "The Loop"
    assert destination("i ride out to the loop") == "The Loop"  # a typed move means the place in any case
