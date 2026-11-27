import cv2
import numpy as np

from tools.loop_still.depth import Drift, depth_path, load_or_make_depth

W, H, N, S = 240, 160, 48, 2.0


def _disp():
    d = np.tile(np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None], (1, W))  # far at the top, near at the bottom
    matte = np.zeros((H, W), np.float32)
    matte[60:150, 100:140] = 1
    d[60:150, 100:140] = 0.9   # she stands nearer than the wall behind her
    return d, matte


def test_cached_depth_is_reused_and_missing_model_gives_none(tmp_path):
    still = tmp_path / "s.png"
    cv2.imwrite(str(still), np.zeros((H, W, 3), np.uint8))
    assert load_or_make_depth(still, tmp_path / "nope") is None
    cv2.imwrite(str(depth_path(still)), (np.linspace(0, 65535, W)[None].repeat(H, 0)).astype(np.uint16))
    d = load_or_make_depth(still, tmp_path / "nope")
    assert d.shape == (H, W) and d.dtype == np.float32 and abs(d[0, -1] - 1) < 1e-3


def test_drift_is_periodic_capped_and_keeps_her_still():
    d, matte = _disp()
    drift = Drift(d, matte, (W, H), N, S, set())
    for i in range(N):
        dx, dy = drift.shift(i)
        assert np.abs(dx).max() <= 0.012 * W + 1e-4 and np.abs(dy).max() <= 0.012 * W + 1e-4
        assert abs(dx[140, 120]) < 0.3 and abs(dy[140, 120]) < 0.3   # at her feet
    a, b = drift.shift(0), drift.shift(N)
    assert np.allclose(a[0], b[0], atol=1e-5) and np.allclose(a[1], b[1], atol=1e-5)
    assert max(np.abs(drift.shift(i)[0][5]).max() for i in range(N)) > 0.5   # the far wall moves
    img = np.random.default_rng(0).random((H, W, 3)).astype(np.float32)
    assert np.allclose(drift.apply(img, 0), drift.apply(img, N), atol=1e-5)
    assert drift.reach >= 0


def test_drift_without_character_focuses_on_the_middle():
    d, _ = _disp()
    drift = Drift(d, np.zeros((H, W), np.float32), (W, H), N, S, set())
    assert any(np.abs(drift.shift(i)[0]).max() > 0 for i in range(N))


def test_behind_her_moves_like_the_wall():
    # Her area is filled from around her, so the band uncovered behind a moved edge drifts with the background.
    d, matte = _disp()
    drift = Drift(d, matte, (W, H), N, S, set())
    dx, _ = drift.shift(3)
    assert abs(dx[100, 120] - dx[100, 95]) < 0.25 * (abs(dx[100, 95]) + 0.05)


def test_hand_edited_rgb_depth_and_overshoot(tmp_path):
    # Review: an RGB depth from an editor crashed, and Lanczos overshoot below 0 wrapped to "nearest" in the fill.
    still = tmp_path / "s.png"
    cv2.imwrite(str(still), np.zeros((H, W, 3), np.uint8))
    cv2.imwrite(str(depth_path(still)), np.full((H, W, 3), 128, np.uint8))
    assert load_or_make_depth(still, tmp_path / "nope").shape == (H, W)
    d, matte = _disp()
    d[0:5] = -0.2
    drift = Drift(d, matte, (W, H), N, S, set())
    assert drift.rel.min() >= -drift.focus - 1e-3
