"""Does each sampled frame of a take show the right characters? Reuses design_check's scene check,
which ranks every cast member against each head it finds (rank 1 = right person came out closest)."""

import json
import shutil
import subprocess
from pathlib import Path

from tools import design_check


def frame_names(cast_slugs: list[str], shot: str, take: str, n: int) -> list[str]:
    who = (["pair"] + cast_slugs[:2]) if len(cast_slugs) > 1 else cast_slugs[:1]
    return ["--".join(who + [f"{shot}-{take}-f{i}"]) + ".png" for i in range(1, n + 1)]


def extract_cmd(video: Path, out_pattern: Path, n: int, seconds: float) -> list[str]:
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"fps={n / seconds:g}",
            "-frames:v", str(n), str(out_pattern)]


def run(short_dir: Path, shot_id: str, take: str, cast_slugs: list[str], seconds: float, n: int = 4) -> dict:
    qa = short_dir / "qa" / f"{shot_id}-{take}"
    shutil.rmtree(qa, ignore_errors=True)
    qa.mkdir(parents=True)
    subprocess.run(extract_cmd(short_dir / "shots" / shot_id / "takes" / f"{take}.mp4", qa / "raw%d.png", n, seconds),
                   check=True)
    for i, name in enumerate(frame_names(cast_slugs, shot_id, take, n), start=1):
        if (qa / f"raw{i}.png").exists():
            (qa / f"raw{i}.png").rename(qa / name)
    design_check.main(["--scenes", "--scenes-dir", str(qa), "--out", str(qa / "scenes.json")])
    return json.loads((qa / "scenes.json").read_text())
