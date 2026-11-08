from pathlib import Path

from tools.shorts import remote


def test_commands_sync_run_and_fetch(tmp_path):
    up, run, down = remote.commands(tmp_path, "pilot")
    assert up[0] == "rsync" and str(tmp_path / "scene.json") in up
    assert run[0] == "ssh" and "-b" in run[-1] and "blender_build.py" in run[-1] and "pilot" in run[-1]
    assert down[0] == "rsync" and down[-1].rstrip("/") == str(tmp_path)


def test_encode_builds_h264_command(tmp_path):
    argv = remote.encode(tmp_path / "frames", tmp_path / "greybox.mp4", 24)
    assert argv[:3] == ["ffmpeg", "-y", "-framerate"] and "libx264" in argv and argv[-1].endswith("greybox.mp4")
