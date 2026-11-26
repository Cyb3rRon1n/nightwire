import numpy as np

from tools.loop_still.periodic import divisors_between, pick_cycles, tile_noise


def test_pick_cycles_shares_no_factor():
    taken = {4}
    c = pick_cycles(0.3, 20, taken)
    assert c in (5, 7) and taken == {4, c}


def test_pick_cycles_never_zero():
    assert pick_cycles(0.01, 10, set()) == 1


def test_pick_cycles_avoids_an_equal_count():
    taken = {6}
    assert pick_cycles(0.3, 20, taken) != 6


def test_divisors_between():
    assert divisors_between(480, 6, 48) == [6, 8, 10, 12, 15, 16, 20, 24, 30, 32, 40, 48]
    assert divisors_between(7, 6, 48) == [7]


def test_tile_noise_wraps():
    n = tile_noise(64, 96, 16, np.random.default_rng(1))
    assert n.shape == (64, 96) and 0 <= n.min() and n.max() <= 1
    step = np.median(np.abs(np.diff(n, axis=1)))
    assert np.abs(n[:, 0] - n[:, -1]).max() < 2 * np.abs(np.diff(n, axis=1)).max()
    assert np.abs(n[:, 0] - n[:, -1]).mean() < 4 * step
