import numpy as np

from tools.loop_still.checks import Checks
from tools.loop_still.periodic import tile_noise

H, W, N, FPS = 64, 96, 48, 12


def _scene():
    still = np.repeat(tile_noise(H, W, 12, np.random.default_rng(1))[..., None], 3, axis=2) * 0.5 + 0.2
    matte = np.zeros((H, W), np.float32); matte[16:56, 36:60] = 1
    face = np.zeros((H, W), np.float32); face[20:28, 42:54] = 1
    return still.astype(np.float32), face, matte


def _frames(still, shift=2):
    return [np.roll(still, shift * i, axis=1) for i in range(N)]


def _run(frames, still, face, matte, char=None, back=None, blink=None, stretch=(1.0, 1.0)):
    c = Checks(still, face, matte, N, FPS, blink_mask=blink)
    for i, f in enumerate(frames):
        c.character(i, char(i) if char else still)
        c.back(i, back(i) if back else still)
        c.stretch(*stretch)
        c.final(i, f)
    return c.result()


def test_clean_periodic_sequence_passes():
    still, face, matte = _scene()
    r = _run(_frames(still), still, face, matte)
    assert r["passed"], r
    assert r["face_max_diff"] == 0 and r["seam_ratio"] <= 1.25 and r["repeat_score"] >= 1.0


def test_planted_seam_fails():
    still, face, matte = _scene()
    frames = _frames(still)
    frames[-1] = np.roll(frames[-1], 20, axis=1)
    r = _run(frames, still, face, matte)
    assert "seam" in r["failed"]


def test_changed_face_pixel_fails():
    still, face, matte = _scene()
    bad = still.copy(); bad[24, 48] += 0.01
    r = _run(_frames(still), still, face, matte, char=lambda i: bad if i == 7 else still)
    assert "face" in r["failed"] and r["face_max_diff"] > 0


def test_blink_pixels_are_exempt():
    still, face, matte = _scene()
    blink = np.zeros((H, W), np.float32); blink[22:25, 44:52] = 1
    eyes = still.copy(); eyes[22:25, 44:52] = 0
    r = _run(_frames(still), still, face, matte, char=lambda i: eyes, blink=blink)
    assert r["face_max_diff"] == 0 and "face" not in r["failed"]


def test_halo_fails_on_a_bright_ring():
    still, face, matte = _scene()
    glow = still.copy(); glow[14:58, 34:62] += 0.3; glow[16:56, 36:60] = still[16:56, 36:60]
    r = _run(_frames(still), still, face, matte, back=lambda i: glow)
    assert "halo" in r["failed"]


def test_hidden_half_loop_fails_repeat():
    still, face, matte = _scene()
    half = _frames(still, shift=4)[: N // 2]
    r = _run(half + half, still, face, matte)
    assert "repeat" in r["failed"] and r["repeat_score"] < 1.0


def test_stretch_out_of_bounds_fails():
    still, face, matte = _scene()
    r = _run(_frames(still), still, face, matte, stretch=(0.85, 1.0))
    assert "stretch" in r["failed"]


def test_empty_matte_gives_none_not_crash():
    still, _, _ = _scene()
    z = np.zeros((H, W), np.float32)
    r = _run(_frames(still), still, z, z)
    assert r["face_max_diff"] is None and r["halo_ratio"] is None and r["passed"]
