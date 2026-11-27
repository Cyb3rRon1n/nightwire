import numpy as np

from tools.loop_still.idle import Idle, spring
from tools.loop_still.motion import Motion

W, H, N, S = 200, 300, 48, 2.0


def _her():
    matte = np.zeros((H, W), np.float32)
    matte[40:290, 70:130] = 1         # head top 40, feet 289
    face = np.zeros((H, W), np.float32)
    face[50:80, 85:115] = 1
    hair = np.zeros((H, W), np.float32)
    hair[40:120, 70:130] = 1
    hair[50:80, 85:115] = 0
    return matte, face, hair


def _field(terms, i):
    dx = np.zeros((H, W), np.float32)
    dy = np.zeros((H, W), np.float32)
    for c, theta, px, qx, py, qy in terms:
        a = 2 * np.pi * c * i / N + theta
        for d, p, q in ((dx, px, qx), (dy, py, qy)):
            if p is not None:
                d += np.sin(a) * p
            if q is not None:
                d -= np.cos(a) * q
    return dx, dy


def test_idle_is_periodic_and_moves():
    matte, face, _ = _her()
    t = Idle(matte, face, (W, H), N, S, 1, set()).terms()
    a, b = _field(t, 0), _field(t, N)
    assert np.allclose(a[0], b[0], atol=1e-4) and np.allclose(a[1], b[1], atol=1e-4)
    assert max(np.abs(_field(t, i)[0]).max() for i in range(N)) > 0.3


def test_face_moves_rigidly():
    matte, face, _ = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    for i in range(0, N, 5):
        assert idle.rigid_error(_field(idle.terms(), i)) < 0.01


def test_feet_stay_planted():
    matte, face, _ = _her()
    t = Idle(matte, face, (W, H), N, S, 1, set()).terms()
    for i in range(N):
        dx, dy = _field(t, i)
        assert abs(dx[289, 100]) < 0.1 and abs(dy[289, 100]) < 0.1


def test_spring_is_one_when_slow_and_lags_when_faster():
    assert abs(spring(0, S, 0.9, 0.3) - 1) < 1e-9
    h = spring(1, 2.0, 0.9, 0.3)    # 0.5 Hz
    assert abs(h) > 1 and np.angle(h) < 0


def test_motion_with_idle_has_a_body_layer_and_loops():
    matte, face, hair = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    body = np.maximum(matte * (1 - hair), face)
    m = Motion({"hair": hair}, face, (W, H), N, S, (-1, 0), 1, idle.taken, idle=idle, body=body)
    assert list(m.regions)[0] == "body"
    img = np.random.default_rng(0).random((H, W, 3)).astype(np.float32)
    for (a, aa), (b, ba) in zip(m.layers(img, 0), m.layers(img, N)):
        assert np.allclose(a, b, atol=1e-4) and np.allclose(aa, ba, atol=1e-4)
    assert m.rigid_error(7) < 0.01
    lo, hi = m.stretch(7)
    assert 0.9 < lo and hi < 1.1


def test_idle_alone_without_hair_or_coat():
    matte, face, _ = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    m = Motion({}, face, (W, H), N, S, (-1, 0), 1, idle.taken, idle=idle, body=np.maximum(matte, face))
    assert list(m.regions) == ["body"]
    moved = m.move(face, 5)
    assert moved.shape == face.shape and moved.sum() > 0


def test_hair_tips_trail_the_head():
    # Springs: the tips of the hair get the extra (H - 1) * body motion, the roots none.
    matte, face, hair = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    with_spring = Motion({"hair": hair}, face, (W, H), N, S, (-1, 0), 1, set(idle.taken), idle=idle,
                         body=np.maximum(matte * (1 - hair), face), amp=0.0)
    head = _field(idle.terms(hair=True), 0)
    dx, dy = with_spring.field(0, "hair")
    assert not np.allclose(dx[115, 75], head[0][115, 75], atol=1e-3)   # a tip


def test_bust_crop_does_not_tear():
    # Review: on a head-and-shoulders still the hips clamp to 2 px under the shoulders and the breath tore the chest.
    from tools.loop_still.motion import stretch
    w = h = 400
    matte = np.zeros((h, w), np.float32)
    matte[20:, 80:320] = 1
    face = np.zeros((h, w), np.float32)
    face[60:200, 140:260] = 1
    idle = Idle(matte, face, (w, h), N, S, 1, set())
    for i in range(0, N, 3):
        dx = np.zeros((h, w), np.float32)
        dy = np.zeros((h, w), np.float32)
        for c, theta, px, qx, py, qy in idle.terms():
            a = 2 * np.pi * c * i / N + theta
            for d, p, q in ((dx, px, qx), (dy, py, qy)):
                if p is not None:
                    d += np.sin(a) * p
                if q is not None:
                    d -= np.cos(a) * q
        lo, hi = stretch(dx, dy, matte >= 0.5)
        assert 0.97 < lo and hi < 1.03, (i, lo, hi)


def test_springs_fold_into_the_idle_terms_and_skip_empty_maps():
    # Review: every idle term was stored twice per region and all-zero maps were multiplied every frame.
    matte, face, hair = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    m = Motion({"hair": hair}, face, (W, H), N, S, (-1, 0), 1, idle.taken, idle=idle,
               body=np.maximum(matte * (1 - hair), face))
    assert len(m.regions["hair"].terms) == 2 + len(idle.terms())
    assert any(p is None for t in m.regions["body"].terms for p in t[2:])


def test_hair_swept_reach_leaves_out_the_shared_body_motion():
    # Review: the halo ring moves with the body, so only motion relative to the body may hide it.
    matte, face, hair = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    m = Motion({"hair": hair}, face, (W, H), N, S, (-1, 0), 1, idle.taken, idle=idle,
               body=np.maximum(matte * (1 - hair), face))
    r = m.regions["hair"]
    assert 0 < r.rel_reach < r.reach


def test_carry_moves_each_part_with_its_own_layer():
    # Review: the sheen on hair rode the body field, so glints slid off the strands.
    matte, face, hair = _her()
    idle = Idle(matte, face, (W, H), N, S, 1, set())
    m = Motion({"hair": hair}, face, (W, H), N, S, (-1, 0), 1, idle.taken, idle=idle,
               body=np.maximum(matte * (1 - hair), face))
    spot = np.zeros((H, W), np.float32)
    spot[110:118, 72:80] = 1   # on a hair tip
    i = 5
    want = m._remap(spot * m.regions["hair"].mask, *m.field(i, "hair"))
    assert np.allclose(m.carry(spot, i), want, atol=1e-4)
