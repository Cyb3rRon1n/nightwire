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


from ruleset.difficulty import Difficulty, difficulty_for


def test_stakes_map_to_difficulty():
    assert difficulty_for("low", []) == ("low", Difficulty.EASY)
    assert difficulty_for("normal", []) == ("normal", Difficulty.MODERATE)
    assert difficulty_for("high", []) == ("high", Difficulty.HARD)
    assert difficulty_for("extreme", []) == ("extreme", Difficulty.EXTREME)


def test_third_high_in_window_is_downgraded():
    recent = ["high", "normal", "extreme", "normal", "low", "normal"]
    assert difficulty_for("high", recent) == ("normal", Difficulty.MODERATE)
    assert difficulty_for("extreme", recent) == ("normal", Difficulty.MODERATE)


def test_twelve_extremes_in_a_row_are_at_most_half_hard_or_above():
    recent: list[str] = []
    hard = 0
    for _ in range(12):
        effective, dc = difficulty_for("extreme", recent)
        recent = (recent + [effective])[-6:]
        hard += dc >= Difficulty.HARD
    assert hard <= 6


def test_only_last_six_count():
    recent = ["high", "high", "normal", "normal", "normal", "normal", "normal", "normal"]
    assert difficulty_for("high", recent) == ("high", Difficulty.HARD)
