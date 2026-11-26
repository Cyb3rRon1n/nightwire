import cv2
import numpy as np
import pytest

from tools.loop_still.blink import Blinks, load_blinks, schedule


def _gaps(sched, frames):
    groups = []  # a double blink counts as one group
    for start, names in sched:
        if groups and start - groups[-1][1] <= 7:
            groups[-1][1] = start + len(names)
        else:
            groups.append([start, start + len(names)])
    starts = [g[0] for g in groups]
    return [b - a for a, b in zip(starts, starts[1:])] + [frames - starts[-1] + starts[0]]


def test_gaps_are_uneven_and_3_to_8_s():
    for seed in range(1, 21):
        sched = schedule(480, 24, seed)
        gaps = _gaps(sched, 480)
        assert all(3 * 24 <= g <= 8 * 24 + 20 for g in gaps), (seed, gaps)
        assert len(set(gaps)) > 1


def test_blink_shapes_follow_the_drawn_timing():
    shapes = {tuple(n) for seed in range(1, 40) for _, n in schedule(480, 24, seed)}
    assert ("half", "closed", "closed", "half", "half") in shapes
    assert all(n[0] == "half" and n[-1] == "half" and "closed" in n for n in shapes)


@pytest.mark.parametrize("frames", [480, 168])
def test_no_blink_straddles_the_seam(frames):
    for seed in range(1, 51):
        for start, names in schedule(frames, 24, seed):
            assert start >= 12 and start + len(names) <= frames - 12


def _patches(h=40, w=60):
    half = np.zeros((h, w, 4), np.float32); half[10:14, 20:30] = (0.5, 0.5, 0.5, 1)
    closed = np.zeros((h, w, 4), np.float32); closed[10:16, 20:30] = (0.1, 0.1, 0.1, 1)
    return half, closed


def test_apply_changes_only_patch_pixels():
    half, closed = _patches()
    b = Blinks(half, closed, 480, 24, 1)
    start, names = b.schedule[0]
    img = np.full((40, 60, 3), 0.8, np.float32)
    out = b.apply(img, start + names.index("closed"))
    changed = np.any(out != img, axis=2)
    assert changed.any() and not changed[~(b.mask > 0)].any()
    assert np.array_equal(b.apply(img, start - 1), img)


def test_load_blinks_needs_both_patches(tmp_path):
    still = tmp_path / "s.png"
    cv2.imwrite(str(still), np.zeros((40, 60, 3), np.uint8))
    half, closed = _patches()
    cv2.imwrite(str(tmp_path / "s.blink-half.png"), (half * 255).astype(np.uint8))
    assert load_blinks(still, 480, 24, 1) is None
    cv2.imwrite(str(tmp_path / "s.blink-closed.png"), (closed * 255).astype(np.uint8))
    b = load_blinks(still, 480, 24, 1, fit=lambda im: cv2.resize(im, (120, 80)))
    assert b is not None and b.mask.shape == (80, 120)


def test_load_blinks_resizes_patches_to_the_still(tmp_path):
    still = tmp_path / "s.png"
    cv2.imwrite(str(still), np.zeros((40, 60, 3), np.uint8))
    for n in ("half", "closed"):
        cv2.imwrite(str(tmp_path / f"s.blink-{n}.png"), np.zeros((20, 20, 4), np.uint8))
    assert load_blinks(still, 480, 24, 1).mask.shape == (40, 60)
