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
    at = [c["dist"] * s * math.sin(yaw), c["dist"] * s * math.cos(yaw), c["height"] * s]
    cam = {"at": at, "lens": c["lens"], "look": [dx * right[0], dx * right[1], c["look"] * s * focus], "dist": c["dist"] * s}
    if "fg" in c:  # stand-in "shoulder" figure just in front of the camera, along the real view axis (which look_dx turns), facing the same way
        vx, vy = cam["look"][0] - at[0], cam["look"][1] - at[1]
        n = math.hypot(vx, vy)
        fwd = (vx / n, vy / n)
        left = (-fwd[1], fwd[0])
        f, side = c["fg"]["forward"] * s, c["fg"]["side"] * s
        cam["fg"] = {"at": [at[0] + fwd[0] * f + left[0] * side, at[1] + fwd[1] * f + left[1] * side, 0.0],
                     "rz": math.degrees(math.atan2(-fwd[0], fwd[1])), "scale": height_cm / presets.RIG_HEIGHT_CM, "rot": presets.POSES["stand"]["rot"]}
    return cam


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


NEEDED = ("board.png", "depth.png", "pose.json", "meta.json")


def commands(out: Path, job: Path = Path("job.json"), todo: list[dict] | None = None) -> list[list[str]]:
    host = remote.BLENDER_HOST
    up = ["rsync", "-a", "--mkpath", str(job), str(LIB), str(presets.BLENDER_BUILD), f"{host}:{REMOTE_DIR}/"]
    run = ["ssh", host, f"cd {shlex.quote(REMOTE_DIR)} && find . -mindepth 1 -maxdepth 1 -type d -exec rm -rf {{}} + && {remote.BLENDER} -b -P blender_library.py -- job.json . "
                        "> blender.log 2>&1 || (tail -30 blender.log; exit 1)"]
    only = []  # pull just this job's cells
    if todo is not None:
        for p in dict.fromkeys(j["pose"] for j in todo):
            only += [f"--include={p}/"] + [f"--include={j['dir']}/***" for j in todo if j["pose"] == p]
        only.append("--exclude=*")
    down = ["rsync", "-a", "--mkpath", *only, f"{host}:{REMOTE_DIR}/", f"{out}/"]
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


def missing(todo: list[dict], out: Path) -> list[str]:
    return [f"{j['dir']}/{f}" for j in todo for f in NEEDED if not (out / j["dir"] / f).exists()]


def build(poses, cameras, height_cm, out: Path | None = None) -> list[dict]:
    out = out or default_out()
    todo = jobs(poses, cameras, height_cm, out)
    with tempfile.TemporaryDirectory() as tmp:
        job = Path(tmp) / "job.json"
        job.write_text(json.dumps({"res": RES, "cells": todo}))
        for argv in commands(out, job, todo):
            subprocess.run(argv, check=True)
    lost = missing(todo, out)
    if lost:
        raise RuntimeError(f"{len(lost)} missing outputs after the Blender run, e.g.: {', '.join(lost[:10])}")
    for j in todo:
        finish(out / j["dir"])
    return todo


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tools.greybox_library")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render poses x cameras on the GPU box")
    b.add_argument("--poses", nargs="+"), b.add_argument("--cameras", nargs="+")
    b.add_argument("--height", type=int, default=presets.REF_HEIGHT_CM, help="figure height in cm")
    b.add_argument("--out", type=Path, default=None, help="default: $NIGHTWIRE_DESIGN_DIR/greybox-library, else design-data/greybox-library")
    i = sub.add_parser("insert", help="put library stand-ins into a plate -> grey draft board")
    i.add_argument("plate", type=Path), i.add_argument("pose"), i.add_argument("camera")
    i.add_argument("--feet", help="x,y 0..1"), i.add_argument("--height", type=float, dest="h", help="figure height as a fraction of frame height")
    i.add_argument("--label", default=""), i.add_argument("--out", type=Path, dest="board", required=True)
    i.add_argument("--lib", type=Path, default=None)
    i.add_argument("--figure", nargs=5, action="append", metavar=("POSE", "CAMERA", "FEET", "HEIGHT", "LABEL"),
                   help="extra figure, repeatable: POSE CAMERA x,y HEIGHT LABEL")
    sub.add_parser("page", help="write the browse-only HTML gallery to design-data/shorts/_site/library/")
    a = ap.parse_args(argv)
    if a.cmd == "page":
        from tools.greybox_library import page
        print(page.build(default_out(), page.site_dir()))
        return
    if a.cmd == "insert":
        from tools.greybox_library import insert
        lib = a.lib or default_out()
        figs = [(a.pose, a.camera, a.feet, a.h, a.label)] if a.feet else []
        figs += [tuple(f) for f in a.figure or []]
        if not figs:
            raise SystemExit("give --feet/--height (first figure) and/or --figure groups")
        todo = []
        for pose, cam, feet, h, label in figs:
            entry = lib / pose / cam
            if not (entry / "board.png").exists():
                raise SystemExit(f"no library cell {pose}/{cam} in {lib}")
            todo.append({"entry": entry, "feet": tuple(float(v) for v in feet.split(",")), "height": float(h), "label": label or f"{pose}"})
        print(insert.insert_many(a.plate, todo, a.board))
        return
    out = a.out or default_out()
    done = build(a.poses, a.cameras, a.height, out)
    print(f"{len(done)} cells -> {out}")
