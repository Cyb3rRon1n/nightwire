import numpy as np
import pytest

from tools.loop_still.layers import RAIN, Fog, Rain, Splashes

SIZE, N = (320, 224), 48


@pytest.mark.parametrize("near", [False, True])
def test_rain_frame_0_equals_frame_N(near):
    r = Rain(SIZE, N, "steady", 1, near=near)
    assert r.layer(0).any() and np.array_equal(r.layer(0), r.layer(N))
    assert not np.array_equal(r.layer(0), r.layer(1))


def test_rain_none_is_empty():
    assert not Rain(SIZE, N, "none", 1).layer(3).any()
    assert RAIN == {"none": 0, "drizzle": 250, "steady": 600, "heavy": 1200}


def test_near_rain_is_sparser_and_brighter_than_far():
    far, near = Rain(SIZE, N, "heavy", 1), Rain(SIZE, N, "heavy", 1, near=True)
    assert len(near.x0) < len(far.x0) and near.alpha.min() > far.alpha.max()


@pytest.mark.parametrize("frames", [480, 168, 252])
def test_splash_periods_divide_N(frames):
    s = Splashes(SIZE, frames, 0.8, 1, count=40)
    assert all(frames % p == 0 for p in s.periods)


def test_splash_lasts_three_frames():
    s = Splashes(SIZE, N, 0.8, 3, count=1)
    on = [bool(s.layer(i).any()) for i in range(N)]
    p = s.periods[0]
    assert sum(on) == 3 * (N // p)
    assert np.array_equal(s.layer(0), s.layer(N))


def test_splashes_stay_in_the_ground_band_and_off_the_character():
    avoid = np.zeros(SIZE[::-1], np.float32); avoid[:, :160] = 1
    s = Splashes(SIZE, N, 0.8, 2, count=30, avoid=avoid)
    total = sum(s.layer(i) for i in range(N))
    assert total[: int(0.8 * SIZE[1]) - 8].max() == 0
    assert total[:, :150].max() == 0


def test_fog_frame_0_equals_frame_N():
    f = Fog(SIZE, N, 1)
    assert np.array_equal(f.layer(0), f.layer(N)) and f.layer(0).max() <= 0.08


def test_same_seed_same_layers():
    assert np.array_equal(Rain(SIZE, N, "steady", 5).layer(7), Rain(SIZE, N, "steady", 5).layer(7))
    assert np.array_equal(Splashes(SIZE, N, 0.8, 5, 20).layer(7), Splashes(SIZE, N, 0.8, 5, 20).layer(7))
