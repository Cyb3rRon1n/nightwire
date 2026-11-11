import json

import numpy as np
from PIL import Image, ImageDraw

from tools.shorts import plate_camera as pc


def test_height_grows_with_distance_below_the_horizon():
    cam = {"horizon_y": 0.4, "cam_height_m": 1.5}
    near, far = pc.figure_height(0.9, cam, 1.7, 170), pc.figure_height(0.6, cam, 1.7, 170)
    assert abs(near - 1.7 * 0.5 / 1.5) < 1e-6 and abs(far - 1.7 * 0.2 / 1.5) < 1e-6
    # a person as tall as the camera height has their head on the horizon wherever they stand
    assert abs(0.9 - pc.figure_height(0.9, {"horizon_y": 0.4, "cam_height_m": 1.7}, 1.7, 170) - 0.4) < 1e-6
    assert pc.figure_height(0.9, cam, 1.7, 150) < near  # shorter character, shorter figure


def test_feet_above_the_horizon_are_refused():
    try:
        pc.figure_height(0.3, {"horizon_y": 0.4, "cam_height_m": 1.5}, 1.7, 170)
    except ValueError as e:
        assert "horizon" in str(e)
    else:
        raise AssertionError("no error")


def test_pose_height_from_a_cell_camera():
    meta = {"res": [1216, 832], "feet": [0.5, 0.8], "horizon_y": 0.4, "camera": {"height": 1.5}, "figure_height_px": 0}
    meta["figure_height_px"] = 1.7 * (0.4 * 832 / 1.5)
    assert abs(pc.pose_height_m(meta) - 1.7) < 1e-6


def test_in_front_mask_marks_only_what_is_nearer_than_the_feet():
    d = np.full((100, 100), 80, np.uint8)
    d[50:70, :] = 200  # a counter band, near
    d[90:, :] = 90     # floor at the feet
    m = np.asarray(pc.in_front_mask(Image.fromarray(d), (0.5, 0.95)))
    assert m[60, 50] == 255 and m[30, 50] == 0 and m[95, 50] == 0


def test_horizon_found_from_a_drawn_corridor(tmp_path):
    im = Image.new("L", (800, 500), 20)
    d = ImageDraw.Draw(im)
    vp = (400, 200)
    for x in range(-400, 1300, 90):  # floor and ceiling lines converging on vp
        d.line((x, 500, *vp), fill=230, width=3)
        d.line((x, 0, *vp), fill=230, width=3)
    f = tmp_path / "c.png"
    im.save(f)
    y, score = pc.horizon_from_lines(f)
    assert y is not None and abs(y - 0.4) < 0.03 and score > 0.5


def test_hand_set_camera_survives_analyse(tmp_path, monkeypatch):
    f = tmp_path / "p.png"
    Image.new("RGB", (64, 48)).save(f)
    pc.set_camera(f, 0.3, 2.0)
    monkeypatch.setattr(pc, "depth_map", lambda p: Image.new("L", (64, 48)))
    cam = pc.analyse(f)
    assert cam["horizon_y"] == 0.3 and cam["cam_height_m"] == 2.0 and cam["source"] == "owner"
    assert pc.load(f)["horizon_y"] == 0.3 and pc.check_image(f, tmp_path / "chk.png").exists()
    json.loads(pc.camera_path(f).read_text())
