import json
import subprocess

import pytest
from PIL import Image

from tools.shorts import plate_camera, stage
from tests.test_shorts_film import BOARD, SHOT, load_short, with_plate_key, world


def _stage_world(tmp_path):
    shorts, films, lib, plates, dd = world(tmp_path, shot=with_plate_key(SHOT) + BOARD)
    plate = dd / "mama-satos-izakaya" / "plates" / "door.png"
    return load_short(shorts / "pilot"), dd, plates, plate


def test_job_needs_a_plate_camera_then_carries_camera_and_figures(tmp_path):
    s, dd, plates, plate = _stage_world(tmp_path)
    with pytest.raises(ValueError, match="camera"):
        stage.job(s, s.shots[0], dd, dd / "shorts" / "pilot", {}, plates)
    plate_camera.set_camera(plate, 0.45, 1.6)
    j = stage.job(s, s.shots[0], dd, dd / "shorts" / "pilot", {"C1": 172}, plates)
    assert (j["horizon_y"], j["cam_height_m"], j["res"]) == (0.45, 1.6, [1000, 600])
    assert [f["label"] for f in j["figures"]] == ["C1"] and j["figures"][0]["feet"] == [0.4, 0.9]
    assert abs(j["figures"][0]["rig"]["scale"] - 1.0) < 1e-6  # 172 cm = the rig's own height
    assert j["shot_dir"].endswith("shots/S01") and json.dumps(j)


def test_owner_export_wins_over_built_board(tmp_path):
    from tools.shorts import boards
    s, dd, plates, plate = _stage_world(tmp_path)
    sd = dd / "shorts" / "pilot" / "shots" / "S01"
    sd.mkdir(parents=True)
    Image.new("RGB", (1000, 600), (10, 200, 10)).save(sd / "board-start.owner.png")
    (sd / "board-start.owner.pose.json").write_text(json.dumps({"C1": {"points": {"neck": [0.5, 0.3]}, "back": False}}))
    lib = plates.parent / "lib"
    out = boards.build(s, dd, dd / "shorts" / "pilot", lib, plates)
    board = Image.open(out[0]).convert("RGB")
    assert board.getpixel((500, 300)) == (10, 200, 10)  # inside the 9:16 window, untouched
    assert (sd / "board-start.pose.png").exists() and (sd / "board-start.owner.png").exists()


@pytest.mark.skipif(not stage.BLENDER.exists(), reason="no local Blender")
def test_real_blender_builds_a_stage_and_exports_a_board(tmp_path):
    s, dd, plates, plate = _stage_world(tmp_path)
    plate_camera.set_camera(plate, 0.45, 1.6)
    j = stage.job(s, s.shots[0], dd, dd / "shorts" / "pilot", {}, plates)
    jp = tmp_path / "job.json"
    jp.write_text(json.dumps(j))
    import shutil
    from pathlib import Path
    Path(j["shot_dir"]).mkdir(parents=True)
    shutil.copy(j["plate_src"], j["plate"])
    addon = tmp_path / "addon" / "nightwire_stage_addon.py"
    addon.parent.mkdir()
    addon.write_text(stage.addon_source())
    blend = Path(j["shot_dir"]) / "stage.blend"
    subprocess.run([str(stage.BLENDER), "-b", "-P", str(stage.SCRIPT), "--", str(jp), str(blend)], check=True, capture_output=True)
    expr = (f"import sys; sys.path.insert(0, {str(addon.parent)!r}); import nightwire_stage_addon as n; n.export('start')")
    subprocess.run([str(stage.BLENDER), "-b", str(blend), "--python-expr", expr], check=True, capture_output=True)
    sd = dd / "shorts" / "pilot" / "shots" / "S01"
    board = Image.open(sd / "board-start.owner.png").convert("L")
    assert board.size == (1000, 600)
    pose = json.loads((sd / "board-start.owner.pose.json").read_text())["C1"]["points"]
    assert pose["lank"] is not None and abs(pose["lank"][1] - 0.9) < 0.03  # the feet stand where the board put them
