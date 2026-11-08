"""Blender runs on the GPU box: push scene.json, render there, pull the results back."""

import functools
import os
import shlex
import subprocess
from pathlib import Path

BLENDER_HOST = os.environ.get("NIGHTWIRE_BLENDER_HOST", "192.168.10.19")
BLENDER = os.environ.get("NIGHTWIRE_BLENDER", "~/opt/blender/blender")
REMOTE_ROOT = "nightwire-shorts"
SCRIPT = Path(__file__).parent / "greybox" / "blender_build.py"


def commands(short_dir: Path, slug: str) -> list[list[str]]:
    remote_dir = f"{REMOTE_ROOT}/{slug}"
    up = ["rsync", "-a", "--mkpath", str(short_dir / "scene.json"), str(SCRIPT), f"{BLENDER_HOST}:{remote_dir}/"]
    run = ["ssh", BLENDER_HOST,
           f"cd {shlex.quote(remote_dir)} && {BLENDER} -b -P blender_build.py -- scene.json . > blender.log 2>&1 || (tail -30 blender.log; exit 1)"]
    down = ["rsync", "-a", "--exclude", "blender_build.py", f"{BLENDER_HOST}:{remote_dir}/", f"{short_dir}/"]
    return [up, run, down]


def run(short_dir: Path, slug: str) -> None:
    for argv in commands(short_dir, slug):
        subprocess.run(argv, check=True)


@functools.cache
def h264_encoder() -> str:
    listing = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=True).stdout
    for name in ("libx264", "libopenh264"):
        if name in listing:
            return name
    raise RuntimeError("no H.264 encoder in ffmpeg; install ffmpeg with libx264 or libopenh264")


def encode(frames_dir: Path, out: Path, fps: int) -> list[str]:
    enc = h264_encoder()
    quality = ["-crf", "20"] if enc == "libx264" else ["-b:v", "4M"]
    return ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "%04d.png"),
            "-c:v", enc, "-pix_fmt", "yuv420p", *quality, str(out)]
