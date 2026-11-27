import numpy as np

from tools.loop_still.realism import Bloom, Ripples, grain, light_map, rain_tint

W, H, N = 320, 224, 48


def _street():
    rng = np.random.default_rng(0)
    img = np.full((H, W, 3), 0.15, np.float32)
    img[H // 2:] += rng.random((H - H // 2, W, 3)).astype(np.float32) * 0.5  # textured street, so a ripple shows
    return img


def test_ripples_are_periodic_and_stay_off_her():
    avoid = np.zeros((H, W), np.float32)
    avoid[100:, 140:180] = 1
    r = Ripples((W, H), N, 24, 0.6, 1, "heavy", avoid)
    img = _street()
    assert np.array_equal(r.apply(img, 0), r.apply(img, N))
    outs = [r.apply(img, i) for i in range(N)]
    assert any(not np.array_equal(o, img) for o in outs)
    top = int(0.6 * H)
    for o in outs:
        assert np.array_equal(o[:top], img[:top])
        assert np.array_equal(o[100:, 140:180], img[100:, 140:180])


def test_ripples_none_preset_is_empty():
    r = Ripples((W, H), N, 24, 0.6, 1, "none")
    img = _street()
    assert r.empty and np.array_equal(r.apply(img, 5), img)


def test_ripples_with_ground_at_bottom_does_not_crash():
    r = Ripples((W, H), N, 24, 1.0, 1, "heavy")
    img = _street()
    assert np.array_equal(r.apply(img, 3), img)


def test_bloom_only_near_bright_neon():
    img = np.zeros((H, W, 3), np.float32)
    img[100:120, 150:170] = (1.0, 0.1, 1.0)  # magenta neon
    out = Bloom(img).apply(img)
    assert out[95, 160].sum() > img[95, 160].sum()   # glow just outside the tube
    assert np.allclose(out[5, 5], img[5, 5], atol=1e-3)
    grey = np.full((H, W, 3), 0.5, np.float32)
    assert np.allclose(Bloom(grey).apply(grey), grey)


def test_rain_is_brighter_under_light():
    img = np.zeros((H, W, 3), np.float32)
    img[:, : W // 2] = 0.9
    t = rain_tint(light_map(img))
    assert t[H // 2, 10].sum() > t[H // 2, W - 10].sum()


def test_grain_is_fresh_per_frame_and_reproducible():
    a, b = grain((H, W), 1, 0), grain((H, W), 1, 1)
    assert a.shape == (H, W, 1)
    assert np.array_equal(a, grain((H, W), 1, 0)) and not np.array_equal(a, b)
    assert 0.005 < float(a.std()) < 0.02
