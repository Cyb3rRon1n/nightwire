import os

import cv2
import numpy as np
import pytest

from tools.loop_still import matte as m


def _still(tmp_path):
    p = tmp_path / "s.png"
    cv2.imwrite(str(p), np.full((40, 60, 3), 30, np.uint8))
    return p


def test_cached_matte_is_reused_and_never_overwritten(tmp_path):
    still = _still(tmp_path)
    cached = tmp_path / ("s" + m.MATTE_SUFFIX)
    want = np.zeros((40, 60), np.uint8); want[10:30, 20:40] = 255
    cv2.imwrite(str(cached), want)
    os.utime(cached, (1, 1))
    got = m.load_or_make_matte(still, tmp_path / "missing.onnx")
    assert got.dtype == np.float32 and got.shape == (40, 60)
    assert got[20, 30] == 1.0 and got[0, 0] == 0.0
    assert cached.stat().st_mtime == 1


def test_redo_without_model_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        m.load_or_make_matte(_still(tmp_path), None, redo=True)


def test_feather_keeps_core_and_background():
    a = np.zeros((60, 60), np.float32); a[15:45, 15:45] = 1
    f = m.feather(a, px=2)
    assert f[30, 30] == 1.0 and f[0, 0] == 0.0
    assert f[30, 15] == 1.0 and 0 < f[30, 14] < 1 and f[30, 11] == 0  # never thinner, softened just outside


def test_decontaminate_only_touches_the_edge_ring():
    a = np.zeros((60, 60), np.float32); a[15:45, 15:45] = 1
    img = np.full((60, 60, 3), 0.2, np.float32); img[:, :15] = 1.0  # bright neon left of her
    img[15:45, 15:18] = 0.9  # a bright fringe on her edge
    out = m.decontaminate(img, a, ring_px=3)
    assert np.array_equal(out[20:40, 25:40], img[20:40, 25:40])  # deep inside: untouched
    assert np.array_equal(out[:, :10], img[:, :10])               # far outside: untouched
    assert out[30, 16].mean() < img[30, 16].mean()                 # fringe pulled toward her inner colour
