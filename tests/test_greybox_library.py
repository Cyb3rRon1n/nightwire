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
            for n in ("depth", "floor-depth", "figure-depth"):
                Image.new("L", (1216, 832)).save(d / f"{n}.png")
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
    assert p["euler"][2] == 0  # faces +Y, the window is at +Y beyond the figure for the ws-back camera
    xs = [(b["at"][0] - b["size"][0] / 2, b["at"][0] + b["size"][0] / 2) for b in p["blocks"]]
    assert min(x[0] for x in xs) == pytest.approx(-0.6) and max(x[1] for x in xs) == pytest.approx(0.6)
    sill = next(b for b in p["blocks"] if b["name"] == "win.sill")
    assert sill["at"][2] == 0.9 and sill["at"][1] > 0.6
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
        view = [cam["look"][0] - cam["at"][0], cam["look"][1] - cam["at"][1]]  # the real view axis
        n = math.hypot(*view)
        fwd = [view[0] / n, view[1] / n]
        along = d[0] * fwd[0] + d[1] * fwd[1]
        lateral = -d[0] * fwd[1] + d[1] * fwd[0]  # + = camera-left (left = forward rotated +90 deg)
        assert along == pytest.approx(1.4, abs=0.01) and sign * lateral == pytest.approx(0.5, abs=0.01)
        assert cam["fg"]["rot"] == presets.POSES["stand"]["rot"]


# --- insert -----------------------------------------------------------------------------------------------------------------

def _cell(tmp, name="c", box=(500, 300, 600, 700), props=None, fg=None, wide=False):
    """Synthetic library cell 1216x832: floor depth by row; the figure is a nearer rectangle (full-row wide if `wide`, so a row-minimum
    would fail); optional prop / foreground rectangles. Feet at the figure box's bottom centre."""
    import numpy as np
    from PIL import Image
    d = tmp / name
    d.mkdir()
    floor = np.tile(np.linspace(0, 200, 832, dtype=np.uint8)[:, None], (1, 1216))
    if wide:
        box = (0, box[1], 1216, box[3])
    figd, depth = floor.copy(), floor.copy()
    figd[box[1]:box[3], box[0]:box[2]] = 250
    depth[box[1]:box[3], box[0]:box[2]] = 250
    if props:
        depth[props[1]:props[3], props[0]:props[2]] = 240
    if fg:
        depth[fg[1]:fg[3], fg[0]:fg[2]] = 255
    for n, a in (("depth", depth), ("floor-depth", floor), ("figure-depth", figd)):
        Image.fromarray(a).convert("RGB").save(d / f"{n}.png")
    Image.new("RGB", (1216, 832), (120, 120, 120)).save(d / "board.png")
    fx, fy = (box[0] + box[2]) / 2 / 1216, box[3] / 832
    (d / "meta.json").write_text(json.dumps({"feet": [fx, fy], "figure_height_px": box[3] - box[1], "res": [1216, 832], "foreground_figure": bool(fg)}))
    (d / "pose.json").write_text(json.dumps({"points": {"neck": [fx, box[1] / 832], "rank": [fx, fy]}, "back": False}))
    return d


def _plate(tmp, size=(1000, 600)):
    from PIL import Image
    p = tmp / "plate.png"
    Image.new("RGB", size, (200, 180, 160)).save(p)
    return p


def _grey_box(img_path):
    """bbox of the figure from its depth patch (the label tag's anti-aliased text also has grey pixels)."""
    import numpy as np
    from PIL import Image
    ys, xs = np.nonzero(np.asarray(Image.open(img_path)))
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def test_insert_places_feet_and_scale_within_2px(tmp_path):
    from PIL import Image
    from tools.greybox_library import insert
    out = insert.insert(_plate(tmp_path), _cell(tmp_path), (0.4, 0.9), 0.5, "C1", tmp_path / "o" / "board.png")
    img = Image.open(out)
    assert img.size == (1000, 600)
    x0, y0, x1, y1 = _grey_box(tmp_path / 'o' / 'board.depth.png')
    assert abs(y1 - 0.9 * 600) <= 2 and abs((y1 - y0) - 0.5 * 600) <= 2
    assert abs((x0 + x1) / 2 - 0.4 * 1000) <= 2
    assert img.getpixel((5, 590)) == (110, 99, 88)  # plate darkened to 55%


def test_insert_label_pose_depth_outputs(tmp_path):
    from PIL import Image
    from tools.greybox_library import insert
    plate = _plate(tmp_path)
    cell = _cell(tmp_path)
    with_label = insert.insert(plate, cell, (0.4, 0.9), 0.5, "C1 sit-stool", tmp_path / "a.png")
    insert.insert(plate, cell, (0.4, 0.9), 0.5, "", tmp_path / "b.png")
    import numpy as np
    assert (np.asarray(Image.open(with_label)) != np.asarray(Image.open(tmp_path / "b.png"))).any()  # tag drawn
    pose = json.loads((tmp_path / "a.pose.json").read_text())["C1 sit-stool"]
    assert pose["points"]["rank"] == pytest.approx([0.4, 0.9], abs=0.003)
    assert pose["points"]["neck"][1] == pytest.approx(0.4, abs=0.003)
    assert Image.open(tmp_path / "a.pose.png").size == (1000, 600) and Image.open(tmp_path / "a.depth.png").size == (1000, 600)
    dep = np.asarray(Image.open(tmp_path / "a.depth.png"))
    assert dep[300, 400] > 200 and dep[10, 10] == 0


def test_insert_two_figures_and_cli(tmp_path, monkeypatch):
    from PIL import Image
    from tools.greybox_library import build as b
    lib = tmp_path / "lib"
    for pose, cam in (("stand", "ws-front"), ("walk", "ws-front")):
        (lib / pose).mkdir(parents=True, exist_ok=True)
        (lib / pose / cam).mkdir()
        c = _cell(tmp_path, f"{pose}x")
        for f in c.iterdir():
            f.rename(lib / pose / cam / f.name)
    plate = _plate(tmp_path)
    b.main(["insert", str(plate), "stand", "ws-front", "--feet", "0.25,0.9", "--height", "0.5", "--label", "C1",
            "--figure", "walk", "ws-front", "0.75,0.9", "0.5", "C2", "--lib", str(lib), "--out", str(tmp_path / "two.png")])
    poses = json.loads((tmp_path / "two.pose.json").read_text())
    assert set(poses) == {"C1", "C2"} and poses["C2"]["points"]["rank"][0] == pytest.approx(0.75, abs=0.003)
    assert Image.open(tmp_path / "two.png").size == (1000, 600)


def test_page_is_static_and_browse_only(tmp_path):
    from tools.greybox_library import page
    c = _cell(tmp_path)
    lib = tmp_path / "lib" / "stand"
    lib.mkdir(parents=True)
    c.rename(lib / "ws-front")
    idx = page.build(tmp_path / "lib", tmp_path / "site").read_text()
    assert "stand/ws-front/board.jpg" in idx and (tmp_path / "site/stand/ws-front/board.jpg").exists()
    assert "<button" not in idx and "innerHTML" not in idx


def test_full_row_figure_has_no_holes_props_and_foreground_shaded_separately(tmp_path):
    import numpy as np
    from tools.greybox_library import insert
    c = _cell(tmp_path, box=(400, 300, 800, 700), props=(300, 500, 400, 700), fg=(0, 100, 100, 832))
    cut = insert.cutout(c)
    assert [col for _, col in cut["layers"]] == [insert.PROPS, insert.FIGURE, insert.FOREGROUND]
    figure = np.asarray(cut["layers"][1][0]) > 0
    assert figure.sum() == 400 * 400  # the whole rectangle, no holes
    assert (np.asarray(cut["layers"][0][0]) > 0).sum() == 100 * 200
    wide = insert.cutout(_cell(tmp_path, "w", wide=True))
    assert (np.asarray(wide["layers"][0][0]) > 0).all()  # a figure spanning every column of its rows is still found


def test_props_are_darker_than_figure_on_the_board(tmp_path):
    from PIL import Image
    from tools.greybox_library import insert
    c = _cell(tmp_path, box=(400, 300, 800, 700), props=(300, 500, 400, 700))
    img = Image.open(insert.insert(_plate(tmp_path, (1216, 832)), c, (0.5, 0.84), 0.48, "C1", tmp_path / "p.png"))
    assert img.getpixel((600, 500)) == insert.FIGURE and img.getpixel((350, 650)) == insert.PROPS


def test_tiny_figure_never_allocates_a_full_cell_upscale_and_zero_height_raises(tmp_path, monkeypatch):
    from PIL import Image
    from tools.greybox_library import insert
    sizes = []
    real = Image.Image.resize
    monkeypatch.setattr(Image.Image, "resize", lambda self, size, *a, **k: (sizes.append(size), real(self, size, *a, **k))[1])
    insert.insert(_plate(tmp_path), _cell(tmp_path, box=(500, 400, 510, 420)), (0.5, 0.9), 0.5, "T", tmp_path / "t.png")
    assert max(w * h for w, h in sizes) <= 1000 * 600  # crop-sized work, bounded by the plate-sized pose.png resize
    bad = _cell(tmp_path, "z")
    meta = json.loads((bad / "meta.json").read_text())
    meta["figure_height_px"] = 0
    (bad / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="figure_height_px is 0"):
        insert.insert(_plate(tmp_path), bad, (0.5, 0.9), 0.5, "Z", tmp_path / "z.png")
