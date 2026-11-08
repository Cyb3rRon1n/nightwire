from test_shorts_model import write
from tools.shorts.greybox.scene import BONES, FPS, POSE_DROP, POSES, scene_json, tint
from tools.shorts.model import load_short


def test_scene_json_converts_seconds_to_frames(tmp_path):
    sj = scene_json(load_short(write(tmp_path / "pilot")))
    assert sj["fps"] == FPS and sj["res"] == [1280, 720]
    shot = sj["shots"][0]
    assert shot["start_frame"] == 0 and shot["end_frame"] == 5 * FPS
    assert shot["camera"][1][0] == 5 * FPS
    c2 = next(f for f in sj["figures"] if f["id"] == "C2")
    assert c2["keys"][1] == [4 * FPS, 0.4, 0.5, 270.0]
    assert sj["frames"] == 5 * FPS
    assert sj["blocks"][0]["name"] == "counter"


def test_poses_only_use_known_bones():
    for pose in POSES.values():
        assert set(pose) <= set(BONES)
    assert {"stand", "sit", "lean_counter", "kneel", "arm_raised"} <= set(POSES)


def test_tint_is_mostly_grey():
    assert tint(None) == [0.6, 0.6, 0.6]
    r, g, b = tint("#ff0000")
    assert 0.65 < r < 0.7 and g < 0.6


def test_scene_json_exports_pose_drop(tmp_path):
    sj = scene_json(load_short(write(tmp_path / "pilot")))
    drops = {f["id"]: f["drop"] for f in sj["figures"]}
    assert drops["C1"] == POSE_DROP["sit"] == 0.5  # hips 0.95 -> 0.45 = thigh-long seat, shins reach the floor
    assert drops["C2"] == 0.0
    assert POSE_DROP["kneel"] == 0.45
