import numpy as np

from tools.loop_still.wet import Drips, Sheen, wash

W, H, N, FPS = 200, 300, 72, 24


def _her():
    matte = np.zeros((H, W), np.float32)
    matte[40:290, 70:130] = 1
    face = np.zeros((H, W), np.float32)
    face[50:80, 85:115] = 1
    hair = np.zeros((H, W), np.float32)
    hair[40:120, 70:130] = 1
    hair[50:80, 85:115] = 0
    hair[120:140, 70:76] = 1          # a strand hanging lower on the left
    coat = np.zeros((H, W), np.float32)
    coat[120:230, 70:130] = 1
    return matte, face, hair, coat


def test_wash_is_zero_without_a_light_change_and_half_on_the_face():
    matte, face, _, _ = _her()
    assert not wash(np.zeros((H, W, 3), np.float32), matte, face).any()
    delta = np.full((H, W, 3), 0.2, np.float32)
    w = wash(delta, matte, face)
    assert w[60, 100, 0] > 0 and abs(w[60, 100, 0] - 0.5 * w[200, 100, 0]) < 1e-3
    assert not w[5, 5].any()


def test_sheen_never_on_the_face():
    matte, face, _, _ = _her()
    still = np.random.default_rng(0).random((H, W, 3)).astype(np.float32)
    s = Sheen(still, matte, face)
    assert s.mask[50:80, 85:115].max() == 0 and s.mask.max() > 0
    g = s.glint(s.mask, np.full((H, W, 3), 0.5, np.float32), np.full((H, W, 3), 0.3, np.float32))
    assert g.shape == (H, W, 3) and g[50:80, 85:115].max() == 0


def test_drips_are_periodic_off_the_face_and_fall():
    matte, face, hair, coat = _her()
    d = Drips({"hair": hair, "coat": coat}, face, (W, H), N, FPS, 1, 0.97)
    assert len(d.drops) > 0
    seen = 0.0
    for i in range(N):
        a = d.layer(i)
        assert np.array_equal(a, d.layer(i + N))
        assert a[50:80, 85:115].max() == 0
        seen += a.sum()
    assert seen > 0


def test_drips_with_no_masks_are_empty():
    _, face, _, _ = _her()
    d = Drips({}, face, (W, H), N, FPS, 1, 0.8)
    assert d.drops == [] and not d.layer(3).any()
