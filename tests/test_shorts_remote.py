from pathlib import Path

import pytest

from tools.shorts import remote


def test_commands_sync_run_and_fetch(tmp_path):
    up, run, down = remote.commands(tmp_path, "pilot")
    assert up[0] == "rsync" and str(tmp_path / "scene.json") in up
    assert run[0] == "ssh" and "-b" in run[-1] and "blender_build.py" in run[-1] and "pilot" in run[-1]
    assert down[0] == "rsync" and down[-1].rstrip("/") == str(tmp_path)


def _ffmpeg_lists(monkeypatch, listing):
    remote.h264_encoder.cache_clear()
    monkeypatch.setattr(remote.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": listing})())


def test_encode_builds_h264_command(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, "h264_encoder", lambda: "libx264")
    argv = remote.encode(tmp_path / "frames", tmp_path / "greybox.mp4", 24)
    assert argv[:3] == ["ffmpeg", "-y", "-framerate"] and "libx264" in argv and "-crf" in argv
    assert argv[-1].endswith("greybox.mp4")


def test_encoder_picks_x264_then_openh264(monkeypatch, tmp_path):
    _ffmpeg_lists(monkeypatch, " V....D libx264  x\n V....D libopenh264  y\n")
    assert remote.h264_encoder() == "libx264"
    _ffmpeg_lists(monkeypatch, " V....D libopenh264  y\n")
    assert remote.h264_encoder() == "libopenh264"
    argv = remote.encode(tmp_path / "f", tmp_path / "o.mp4", 24)
    assert "libopenh264" in argv and "-b:v" in argv and "-crf" not in argv
    remote.h264_encoder.cache_clear()


def test_encoder_missing_raises(monkeypatch):
    _ffmpeg_lists(monkeypatch, " V....D mpeg4\n")
    with pytest.raises(RuntimeError, match="no H.264 encoder"):
        remote.h264_encoder()
    remote.h264_encoder.cache_clear()
