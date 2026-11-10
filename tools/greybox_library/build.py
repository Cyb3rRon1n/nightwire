"""python -m tools.greybox_library build [--poses ...] [--cameras ...] [--height 165]

Renders every pose x camera in ONE Blender run on the GPU box (same rsync / ssh / rsync pattern as tools/shorts/remote.py) into
design-data/greybox-library/<pose>/<camera>/{board,depth}.png + pose.json + meta.json, then draws pose.png and the horizon line here."""

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from tools.greybox_library import presets
from tools.shorts import guides, remote

LIB = Path(__file__).with_name("blender_library.py")
REMOTE_DIR = "nightwire-greybox"


def default_out() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "greybox-library"


RES = [guides.KEY_W, guides.KEY_H]


def _pick(chosen, available, what):
    chosen = list(chosen or available)
    bad = [c for c in chosen if c not in available]
    if bad:
        raise SystemExit(f"unknown {what}: {', '.join(bad)} (have: {', '.join(available)})")
    return chosen


def _cam(c, height_cm, focus):
    s = height_cm / presets.REF_HEIGHT_CM
    yaw = math.radians(c["yaw"])
    right = (-math.cos(yaw), math.sin(yaw))  # camera's right-hand direction on the floor
    dx = c.get("look_dx", 0.0) * s
    return {"at": [c["dist"] * s * math.sin(yaw), c["dist"] * s * math.cos(yaw), c["height"] * s], "lens": c["lens"],
            "look": [dx * right[0], dx * right[1], c["look"] * s * focus], "dist": c["dist"] * s}


def jobs(poses, cameras, height_cm, out: Path) -> list[dict]:
    """One dict per pose x camera: everything Blender needs, already scaled to the figure height."""
    poses, cameras = _pick(poses, list(presets.POSES), "pose"), _pick(cameras, list(presets.CAMERAS), "camera")
    scale = height_cm / presets.RIG_HEIGHT_CM
    result = []
    for p in poses:
        pose = presets.POSES[p]
        rig = {"rot": pose.get("rot", {}), "euler": pose.get("euler", (0, 0, 0)), "scale": scale,
               "pos": [v * scale for v in pose.get("pos", (0, 0, 0))]}
        for c in cameras:
            result.append({"pose": p, "camera": c, "dir": f"{p}/{c}", "rig": rig, "blocks": pose.get("blocks", []),
                           "cam": _cam(presets.CAMERAS[c], height_cm, pose.get("focus", 1.0))})
    return result


def commands(out: Path, job: Path = Path("job.json")) -> list[list[str]]:
    host = remote.BLENDER_HOST
    up = ["rsync", "-a", "--mkpath", str(job), str(LIB), str(presets.BLENDER_BUILD), f"{host}:{REMOTE_DIR}/"]
    run = ["ssh", host, f"cd {shlex.quote(REMOTE_DIR)} && {remote.BLENDER} -b -P blender_library.py -- job.json . "
                        "> blender.log 2>&1 || (tail -30 blender.log; exit 1)"]
    down = ["rsync", "-a", "--mkpath", "--exclude", "*.py", "--exclude", "job.json", "--exclude", "blender.log", f"{host}:{REMOTE_DIR}/", f"{out}/"]
    return [up, run, down]


def finish(cell: Path) -> None:
    """pose.png from pose.json, and the horizon line on board.png (Blender only knows the floor edge)."""
    pose = json.loads((cell / "pose.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "guide").mkdir()
        (Path(tmp) / "guide" / "p-pose.json").write_text(json.dumps({"f": pose}))
        shutil.copy(guides.pose_image(Path(tmp), "p", {"f"}), cell / "pose.png")
    y = json.loads((cell / "meta.json").read_text()).get("horizon_y")
    if y is not None and 0 <= y <= 1:
        board = Image.open(cell / "board.png").convert("RGB")
        row = round(y * (board.height - 1))
        ImageDraw.Draw(board).line([(0, row), (board.width, row)], fill=(70, 70, 74), width=2)
        board.save(cell / "board.png")


def build(poses, cameras, height_cm, out: Path | None = None) -> list[dict]:
    out = out or default_out()
    todo = jobs(poses, cameras, height_cm, out)
    with tempfile.TemporaryDirectory() as tmp:
        job = Path(tmp) / "job.json"
        job.write_text(json.dumps({"res": RES, "cells": todo}))
        for argv in commands(out, job):
            subprocess.run(argv, check=True)
    for j in todo:
        if (out / j["dir"] / "pose.json").exists():
            finish(out / j["dir"])
    return todo


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tools.greybox_library")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render poses x cameras on the GPU box")
    b.add_argument("--poses", nargs="+"), b.add_argument("--cameras", nargs="+")
    b.add_argument("--height", type=int, default=presets.REF_HEIGHT_CM, help="figure height in cm")
    b.add_argument("--out", type=Path, default=None, help="default: $NIGHTWIRE_DESIGN_DIR/greybox-library, else design-data/greybox-library")
    a = ap.parse_args(argv)
    out = a.out or default_out()
    done = build(a.poses, a.cameras, a.height, out)
    print(f"{len(done)} cells -> {out}")
