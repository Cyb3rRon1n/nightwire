from ruleset.difficulty import Difficulty


def test_difficulty_bands_match_spec_values():
    assert Difficulty.EASY == 6
    assert Difficulty.MODERATE == 9
    assert Difficulty.HARD == 12
    assert Difficulty.EXTREME == 15


def test_difficulty_is_usable_as_a_plain_int():
    # DCs get added/compared against roll totals elsewhere - must behave
    # as a real int, not just a named constant.
    assert Difficulty.MODERATE + 1 == 10
    assert Difficulty.HARD > Difficulty.EASY
