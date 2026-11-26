import numpy as np

from tools.loop_still.motion import Motion, weights
from tools.loop_still.regions import clean_regions

W, H, N = 240, 400, 48


def _masks(w=W, h=H):
    face = np.zeros((h, w), np.float32); face[100:160, 90:150] = 1
    hair = np.zeros((h, w), np.float32); hair[60:300, 60:180] = 1; hair[100:160, 90:150] = 0
    coat = np.zeros((h, w), np.float32); coat[200:390, 50:190] = 1; coat[200:300, 60:180] = 0
    return hair, coat, face


def _motion(**kw):
    hair, coat, face = _masks()
    return Motion({"hair": hair, "coat": coat}, face, (W, H), N, 2.0, (-1.0, 0.0), 1, set(), **kw)


def test_field_at_frame_0_equals_frame_N():
    m = _motion()
    for a, b in zip(m.field(0), m.field(N)):
        assert np.allclose(a, b, atol=1e-6)


def test_roots_and_face_move_zero():
    _, _, face = _masks()
    for i in range(0, N, 10):
        dx, dy = _motion().field(i)  # breathing on: the face still never moves
        assert np.abs(dx[face > 0]).max() == 0 and np.abs(dy[face > 0]).max() == 0
    m = _motion(breath=0)  # breathing lifts the shoulders, so roots are checked without it
    for name, r in m.regions.items():
        for i in range(0, N, 10):
            dx, dy = m.field(i, name)
            assert np.abs(dx[r.roots > 0]).max() == 0 and np.abs(dy[r.roots > 0]).max() == 0


def test_tips_move_most():
    m = _motion(breath=0)
    peak = max(np.hypot(*m.field(i))[280:300, 60:180].max() for i in range(N))
    assert peak >= 0.6 * 0.01 * H


def test_stretch_stays_in_bounds():
    m = _motion()
    lo, hi = min(m.stretch(i)[0] for i in range(N)), max(m.stretch(i)[1] for i in range(N))
    assert 0.9 <= lo and hi <= 1.1


def test_masks_of_another_size_are_resized():
    hair, coat, face = _masks(120, 200)
    m = Motion({"hair": hair, "coat": coat}, face, (W, H), N, 2.0, (-1.0, 0.0), 1, set())
    assert m.field(5)[0].shape == (H, W)


def test_hair_at_frame_edge_reflects_not_black():
    face = np.zeros((H, W), np.float32); face[100:150, 100:150] = 1
    hair = np.zeros((H, W), np.float32); hair[40:300, 0:110] = 1; hair[100:150, 100:110] = 0
    m = Motion({"hair": hair}, face, (W, H), N, 2.0, (-1.0, 0.0), 1, set(), amp=0.03)
    img = np.repeat(np.linspace(0.4, 0.9, W, dtype=np.float32)[None, :, None], H, axis=0).repeat(3, axis=2)
    for i in range(0, N, 6):
        assert m.warp(img, i).min() >= img.min() - 0.02  # no black wedge pulled in


def test_no_regions_is_identity():
    m = Motion({}, np.zeros((H, W), np.float32), (W, H), N, 2.0, (-1.0, 0.0), 1, set())
    img = np.random.default_rng(0).random((H, W, 3)).astype(np.float32)
    assert np.array_equal(m.warp(img, 7), img)


def test_weights_zero_at_root_one_at_tip():
    region = np.zeros((50, 20), np.float32); region[5:45] = 1
    root = np.zeros_like(region); root[5] = 1
    w = weights(region, root)
    assert w[5].max() == 0 and np.isclose(w[44].max(), 1) and w[0].max() == 0


def test_clean_regions_subtracts_face_and_clips_to_matte():
    matte = np.zeros((10, 10), np.float32); matte[:, :8] = 1
    hair = np.ones((10, 10), np.float32); coat = np.ones((10, 10), np.float32); coat[:5] = 0
    face = np.zeros((10, 10), np.float32); face[2:4, 2:4] = 1
    h, c, f = clean_regions(hair, coat, face, matte)
    assert h[2, 2] == 0 and h[0, 9] == 0 and h[0, 0] == 1
    assert c[7, 0] == 0  # a pixel belongs to one region: hair wins over coat
    assert np.array_equal(f, face)


def test_clean_regions_drops_stray_specks():
    matte = np.ones((100, 100), np.float32)
    coat = np.zeros((100, 100), np.float32); coat[10:90, 10:40] = 1; coat[50:52, 70:72] = 1  # a tail and a speck
    face = np.zeros_like(coat)
    _, c, _ = clean_regions(np.zeros_like(coat), coat, face, matte)
    assert c[50, 70] == 0 and c[50, 20] == 1


def test_short_hair_moves_at_most_six_percent_of_its_length():
    face = np.zeros((H, W), np.float32); face[100:160, 90:150] = 1
    hair = np.zeros((H, W), np.float32); hair[80:170, 80:160] = 1; hair[100:160, 90:150] = 0  # a short bob
    m = Motion({"hair": hair}, face, (W, H), N, 2.0, (-1.0, 0.0), 1, set())
    far = max(np.hypot(*m.field(i, "hair")).max() for i in range(N))
    assert far <= 0.06 * 20 * 1.2 + 1e-3  # tips about 20 px from the roots
    lo, hi = min(m.stretch(i)[0] for i in range(N)), max(m.stretch(i)[1] for i in range(N))
    assert 0.9 <= lo and hi <= 1.1


def test_field_outside_two_parts_has_no_seam():
    coat = np.zeros((H, W), np.float32); coat[150:390, 30:90] = 1; coat[150:250, 150:210] = 1  # tails of two lengths
    m = Motion({"coat": coat}, np.zeros((H, W), np.float32), (W, H), N, 2.0, (-1.0, 0.0), 1, set(), breath=0)
    for i in range(0, N, 8):
        dx, _ = m.field(i, "coat")
        assert np.abs(np.diff(dx[240:390, 90:150], axis=1)).max() < 0.1  # between the tails, where the nearest part switches


def test_coat_weight_depends_on_height_below_the_shoulders_only():
    region = np.zeros((200, 200), np.float32); region[20:190, 40:160] = 1
    root = np.zeros_like(region); root[20:30, 90:110] = 1  # a narrow hood top
    w = weights(region, root, hanging=True)
    assert np.allclose(w[150, 45], w[150, 150]) and w[150, 100] > w[60, 100]
