import json
import py_compile
from pathlib import Path

import pytest

from tools.greybox_library import build, presets

BLENDER_LIB = Path(build.__file__).with_name("blender_library.py")


def test_poses_use_only_real_bones_and_have_the_required_set():
    names = set(presets.bone_names())
    assert len(names) == 11 and {"hips", "thigh.L", "forearm.R"} <= names
    required = {"stand", "walk", "sit-stool", "sit-ledge", "lean-rail", "stand-back", "stand-window-back", "crouch", "lie-side", "sit-floor"}
    assert required <= set(presets.POSES)
    for pid, p in presets.POSES.items():
        assert set(p.get("rot", {})) <= names, pid
        assert all(len(v) == 3 for v in p.get("rot", {}).values()), pid
        for b in p.get("blocks", []):
            assert len(b["size"]) == 3 and len(b["at"]) == 3 and b["name"]


def test_props_match_the_brief():
    stool = presets.POSES["sit-stool"]["blocks"][0]
    assert stool["size"][2] == 0.65
    rail = presets.POSES["lean-rail"]["blocks"][0]
    assert rail["at"][2] + rail["size"][2] == pytest.approx(1.05)
    assert presets.POSES["stand-back"]["euler"][2] == 180


def test_cameras_complete_and_ids_slug_safe():
    required = {"ews-high", "ws-front", "ws-back", "ws-profile", "ms-front", "ms-profile", "mcu-front", "ots-left", "ots-right", "low-hero", "top-down"}
    assert required <= set(presets.CAMERAS)
    for cid, c in presets.CAMERAS.items():
        assert {"dist", "height", "yaw", "lens", "look"} <= set(c), cid
    for key in (*presets.POSES, *presets.CAMERAS):
        assert presets.SLUG.match(key), key


def test_jobs_are_pose_times_camera_with_output_paths(tmp_path):
    jobs = build.jobs(["stand", "walk"], ["ws-front", "top-down"], 165, tmp_path)
    assert [(j["pose"], j["camera"]) for j in jobs] == [("stand", "ws-front"), ("stand", "top-down"), ("walk", "ws-front"), ("walk", "top-down")]
    assert jobs[0]["dir"] == "stand/ws-front" and (tmp_path / jobs[0]["dir"]).as_posix().endswith("stand/ws-front")
    assert len(build.jobs(None, None, 165, tmp_path)) == len(presets.POSES) * len(presets.CAMERAS)
    with pytest.raises(SystemExit):
        build.jobs(["nope"], None, 165, tmp_path)


def test_camera_resolution_scales_with_height_and_aims_at_the_figure(tmp_path):
    a = build.jobs(["stand"], ["ws-profile"], 165, tmp_path)[0]["cam"]
    b = build.jobs(["stand"], ["ws-profile"], 330, tmp_path)[0]["cam"]
    assert a["at"][0] == pytest.approx(4.5) and abs(a["at"][1]) < 1e-9 and a["at"][2] == pytest.approx(1.5)
    assert b["at"][0] == pytest.approx(9.0) and a["lens"] == b["lens"] == 35
    focus = build.jobs(["lie-side"], ["ws-front"], 165, tmp_path)[0]["cam"]
    assert focus["look"][2] < a["look"][2]


def test_rig_scale_and_pos_follow_height(tmp_path):
    j = build.jobs(["walk"], ["ws-front"], 86, tmp_path)[0]["rig"]
    assert j["scale"] == pytest.approx(0.5) and j["pos"][2] == pytest.approx(-0.042)


def test_remote_commands_ship_both_scripts_and_pull_results(tmp_path):
    up, run, down = build.commands(tmp_path)
    assert str(build.LIB) in up and str(presets.BLENDER_BUILD) in up and any(a.endswith("job.json") for a in up)
    assert "blender_library.py" in run[-1] and "job.json" in run[-1]
    assert down[-1] == f"{tmp_path}/" and any(a.endswith("/") and ":" in a for a in down)


def test_build_runs_remote_then_writes_pose_png(tmp_path, monkeypatch):
    calls = []

    def fake_run(argv, check):
        calls.append(argv[0])
        if argv[0] == "rsync" and ":" in argv[-2]:  # the pull: fake Blender output
            d = tmp_path / "stand" / "ws-front"
            d.mkdir(parents=True)
            from PIL import Image
            Image.new("RGB", (1216, 832), "grey").save(d / "board.png")
            (d / "pose.json").write_text(json.dumps({"points": {"neck": [0.5, 0.4], "nose": [0.5, 0.3]}, "back": False}))
            (d / "meta.json").write_text(json.dumps({"horizon_y": 0.3}))

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    build.build(["stand"], ["ws-front"], 165, tmp_path)
    assert calls == ["rsync", "ssh", "rsync"]
    assert (tmp_path / "stand" / "ws-front" / "pose.png").exists()
    assert not (tmp_path / "job.json").exists()


def test_blender_script_compiles_and_needs_only_names_that_exist():
    py_compile.compile(str(BLENDER_LIB), doraise=True)
    import ast
    defined = {n.name for n in ast.parse(presets.BLENDER_BUILD.read_text()).body if isinstance(n, ast.FunctionDef)}
    assert {"mannequin", "screen_box", "figure_pose", "render_depth", "render_still"} <= defined
