import pytest

from ruleset.resolution import Outcome, resolve_roll


def test_clean_success_when_total_beats_dc_by_5_or_more():
    # die=8, mods=+2 -> total 10, DC 5 -> beats by 5
    assert resolve_roll(die_result=8, attribute_mod=1, skill_mod=1, dc=5) == Outcome.CLEAN_SUCCESS


def test_complication_when_total_meets_dc_but_not_by_5():
    # die=5, mods=+2 -> total 7, DC 6 -> meets but doesn't beat by 5
    assert resolve_roll(die_result=5, attribute_mod=1, skill_mod=1, dc=6) == Outcome.COMPLICATION


def test_failure_when_total_is_below_dc():
    # die=3, mods=0 -> total 3, DC 10
    assert resolve_roll(die_result=3, attribute_mod=0, skill_mod=0, dc=10) == Outcome.FAILURE


def test_natural_10_is_always_at_least_clean_success():
    # die=10 but mods are so negative the raw total would fail against a
    # high DC - the natural 10 rule overrides the math entirely.
    assert resolve_roll(die_result=10, attribute_mod=-4, skill_mod=-4, dc=20) == Outcome.CLEAN_SUCCESS


def test_natural_1_is_always_failure():
    # die=1 but mods are so high the raw total would clear a low DC - the
    # natural 1 rule overrides the math entirely.
    assert resolve_roll(die_result=1, attribute_mod=5, skill_mod=5, dc=8) == Outcome.FAILURE


def test_boundary_exactly_at_dc_plus_5_is_clean_success():
    # die=5, mods=0, dc=0 -> total 5, exactly dc+5 -> clean success, not complication
    assert resolve_roll(die_result=5, attribute_mod=0, skill_mod=0, dc=0) == Outcome.CLEAN_SUCCESS


def test_boundary_one_below_dc_plus_5_is_complication_not_clean():
    assert resolve_roll(die_result=4, attribute_mod=0, skill_mod=0, dc=0) == Outcome.COMPLICATION


def test_boundary_exactly_at_dc_is_complication():
    assert resolve_roll(die_result=6, attribute_mod=1, skill_mod=1, dc=8) == Outcome.COMPLICATION  # total 8 == dc


def test_boundary_one_below_dc_is_failure():
    assert resolve_roll(die_result=5, attribute_mod=1, skill_mod=1, dc=8) == Outcome.FAILURE  # total 7


def test_die_result_out_of_range_raises():
    with pytest.raises(ValueError):
        resolve_roll(die_result=0, attribute_mod=0, skill_mod=0, dc=10)
    with pytest.raises(ValueError):
        resolve_roll(die_result=11, attribute_mod=0, skill_mod=0, dc=10)
