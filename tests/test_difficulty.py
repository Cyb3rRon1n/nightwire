from ruleset.difficulty import Difficulty


def test_difficulty_bands_match_spec_values():
    assert Difficulty.EASY == 8
    assert Difficulty.MODERATE == 12
    assert Difficulty.HARD == 16
    assert Difficulty.EXTREME == 20


def test_difficulty_is_usable_as_a_plain_int():
    # DCs get added/compared against roll totals elsewhere - must behave
    # as a real int, not just a named constant.
    assert Difficulty.MODERATE + 1 == 13
    assert Difficulty.HARD > Difficulty.EASY
