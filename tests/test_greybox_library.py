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
            Image.new("L", (1216, 832)).save(d / "depth.png")
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


def test_every_name_blender_library_extracts_exists_in_blender_build():
    import ast
    want = {}
    for n in ast.parse(BLENDER_LIB.read_text()).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("WANT_NAMES", "WANT_FUNCS"):
            want[n.targets[0].id] = ast.literal_eval(n.value)
    assert set(want) == {"WANT_NAMES", "WANT_FUNCS"}
    body = ast.parse(presets.BLENDER_BUILD.read_text()).body
    funcs = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    names = {n.targets[0].id for n in body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    assert want["WANT_FUNCS"] <= funcs and want["WANT_NAMES"] <= names


def test_default_output_follows_design_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(tmp_path))
    assert build.default_out() == tmp_path / "greybox-library"
    monkeypatch.delenv("NIGHTWIRE_DESIGN_DIR")
    assert build.default_out() == Path("design-data/greybox-library")


def test_partial_result_raises_and_lists_missing_cells(tmp_path, monkeypatch):
    def fake_run(argv, check):
        if argv[0] == "rsync" and ":" in argv[-2]:
            d = tmp_path / "stand" / "ws-front"
            d.mkdir(parents=True)
            (d / "board.png").write_bytes(b"x")  # no depth/pose/meta, and ws-back never rendered

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as e:
        build.build(["stand"], ["ws-front", "ws-back"], 165, tmp_path)
    assert "stand/ws-front/depth.png" in str(e.value) and "stand/ws-back/board.png" in str(e.value)


def test_stale_remote_cells_are_cleared_and_not_pulled(tmp_path):
    todo = build.jobs(["stand", "walk"], ["ws-front"], 165, tmp_path)
    up, run, down = build.commands(tmp_path, todo=todo)
    assert "rm -rf" in run[-1] and run[-1].index("rm -rf") < run[-1].index("-b -P")
    assert "--include=stand/ws-front/***" in down and "--include=walk/" in down
    assert down.index("--exclude=*") < down.index(down[-2])


def test_window_frame_is_upright_centred_and_in_front_of_the_face():
    p = presets.POSES["stand-window-back"]
    assert p["euler"][2] == 180  # faces -Y, the window is at -Y
    xs = [(b["at"][0] - b["size"][0] / 2, b["at"][0] + b["size"][0] / 2) for b in p["blocks"]]
    assert min(x[0] for x in xs) == pytest.approx(-0.6) and max(x[1] for x in xs) == pytest.approx(0.6)
    sill = next(b for b in p["blocks"] if b["name"] == "win.sill")
    assert sill["at"][2] == 0.9 and sill["at"][1] < -0.6
    top = max(b["at"][2] + b["size"][2] for b in p["blocks"])
    assert top - 0.9 == pytest.approx(1.6, abs=0.02)


def test_arm_only_and_lying_poses_actually_move_big_bones():
    assert presets.POSES["lean-rail"]["rot"]["spine"][0] == -20
    assert max(abs(v) for v in presets.POSES["lean-rail"]["rot"]["forearm.L"]) >= 20  # assert_posed checks these in Blender
    assert presets.POSES["lie-side"]["euler"][1] == 90 and 0.2 <= presets.POSES["lie-side"]["pos"][2] <= 0.3


def test_ots_cameras_get_a_foreground_figure_on_the_matching_side(tmp_path):
    left = build.jobs(["stand"], ["ots-left"], 165, tmp_path)[0]["cam"]
    right = build.jobs(["stand"], ["ots-right"], 165, tmp_path)[0]["cam"]
    assert "fg" not in build.jobs(["stand"], ["ms-front"], 165, tmp_path)[0]["cam"]
    for cam, sign in ((left, 1), (right, -1)):
        import math
        d = [cam["fg"]["at"][0] - cam["at"][0], cam["fg"]["at"][1] - cam["at"][1]]
        view = [-cam["at"][0], -cam["at"][1]]  # camera looks at the origin (horizontally)
        n = math.hypot(*view)
        fwd = [view[0] / n, view[1] / n]
        along = d[0] * fwd[0] + d[1] * fwd[1]
        lateral = d[0] * fwd[1] * -1 + d[1] * fwd[0]  # + = camera-left (left = forward rotated +90 deg)
        assert along == pytest.approx(0.9 * 165 / 165, abs=0.01) and sign * lateral == pytest.approx(0.45, abs=0.01)
        assert cam["fg"]["rot"] == presets.POSES["stand"]["rot"]
