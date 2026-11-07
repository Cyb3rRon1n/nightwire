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
