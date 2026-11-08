"""Rough cut: kept takes in shot order, a music bed, burned subtitles from the script's exact lines."""

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from tools.shorts import remote
from tools.shorts.model import Short


def kept_takes(short: Short, work: Path) -> list[Path]:
    out = []
    for shot in short.shots:
        sd = work / "shots" / shot.id
        v = json.loads((sd / "verdicts.json").read_text()) if (sd / "verdicts.json").exists() else {}
        kept = sorted(t for t, x in v.items() if x.get("verdict") == "keep" and (sd / "takes" / f"{t}.mp4").exists())
        if kept:
            out.append(sd / "takes" / f"{kept[-1]}.mp4")
    return out


def _ts(sec: float) -> str:
    ms = round(sec * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(short: Short, kept_shots: list[str]) -> str:
    blocks, clock, n = [], 0.0, 0
    for shot in short.shots:
        if shot.id not in kept_shots:
            continue
        lines = sorted(shot.lines, key=lambda ln: ln.t)
        for i, ln in enumerate(lines):
            end = lines[i + 1].t if i + 1 < len(lines) else shot.end
            n += 1
            blocks.append(f"{n}\n{_ts(clock + ln.t - shot.start)} --> {_ts(clock + end - shot.start)}\n{ln.text}\n")
        clock += shot.duration
    return "\n".join(blocks)


def _quality() -> list[str]:
    enc = remote.h264_encoder()
    return ["-c:v", enc, *(["-crf", "20"] if enc == "libx264" else ["-b:v", "4M"])]


def concat_cmd(takes: list[Path], listfile: Path, music: Path | None, srt_path: Path, out: Path) -> list[str]:
    listfile.write_text("".join(f"file '{t}'\n" for t in takes))
    argv = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listfile)]
    vf = f"subtitles={srt_path}"
    if music:
        argv += ["-stream_loop", "-1", "-i", str(music),
                 "-filter_complex", f"[0:v]{vf}[v];[1:a]volume=0.25[m];[0:a][m]amix=inputs=2:duration=first[a]",
                 "-map", "[v]", "-map", "[a]"]
    else:
        argv += ["-vf", vf]
    return argv + [*_quality(), "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    streams = json.loads(out)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    return {"audio": any(s["codec_type"] == "audio" for s in streams),
            "size": (v["width"], v["height"]), "fps": float(Fraction(v["r_frame_rate"]))}


def needs_normalise(infos: list[dict]) -> bool:
    """True when any take lacks audio, or sizes/fps differ (concat demuxer needs them identical)."""
    return (not all(i["audio"] for i in infos)
            or len({i["size"] for i in infos}) > 1 or len({round(i["fps"], 2) for i in infos}) > 1)


def norm_cmd(src: Path, dst: Path, has_audio: bool) -> list[str]:
    argv = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
    if not has_audio:
        argv += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest"]
    return argv + ["-vf", "scale=1280:720,fps=24", *_quality(), "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", str(dst)]
