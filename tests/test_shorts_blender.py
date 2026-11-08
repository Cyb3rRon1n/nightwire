import json
import os
import subprocess
from pathlib import Path

import pytest

BLENDER = os.environ.get("NIGHTWIRE_BLENDER")
pytestmark = pytest.mark.skipif(not BLENDER, reason="set NIGHTWIRE_BLENDER to a local blender binary")


def test_two_figure_room_renders(tmp_path):
    scene = {"fps": 24, "res": [320, 180], "frames": 48,
             "blocks": [{"name": "counter", "size": [2, 0.5, 1], "at": [0, 1, 0], "rot": 0}],
             "figures": [{"id": "C1", "tier": "mannequin", "pose": "sit", "rotations": {"thigh.L": [90, 0, 0]},
                          "tint": [0.6, 0.6, 0.6], "keys": [[0, -0.5, 0, 90]]},
                         {"id": "C2", "tier": "capsule", "pose": "stand", "rotations": {}, "tint": [0.6, 0.6, 0.6],
                          "keys": [[0, 0.5, 0, 270], [24, 0.2, 0, 270]]}],
             "shots": [{"id": "S01", "start_frame": 0, "end_frame": 24, "lens": 35,
                        "camera": [[0, [-3, -3, 1.6], [0, 0, 1]], [23, [-2.5, -2.5, 1.5], [0, 0, 1]]]},
                       {"id": "S02", "start_frame": 24, "end_frame": 48, "lens": 50,
                        "camera": [[24, [3, -3, 1.6], [0, 0, 1]], [47, [2.5, -2.5, 1.5], [0, 0, 1]]]}]}
    (tmp_path / "scene.json").write_text(json.dumps(scene))
    script = Path(__file__).parents[1] / "tools" / "shorts" / "greybox" / "blender_build.py"
    subprocess.run([BLENDER, "-b", "-P", str(script), "--", str(tmp_path / "scene.json"), str(tmp_path)], check=True)
    assert (tmp_path / "scene.blend").exists() and (tmp_path / "floorplan.png").exists()
    for shot in ("S01", "S02"):
        names = sorted(p.name for p in (tmp_path / "shots" / shot / "frames").glob("*.png"))
        assert names == [f"{i:04d}.png" for i in range(24)]
        assert {p.name for p in (tmp_path / "shots" / shot / "preview").iterdir()} == {"start.png", "middle.png", "end.png"}
