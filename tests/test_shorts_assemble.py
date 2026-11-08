import json

import pytest
from test_shorts_model import write
from tools.shorts.assemble import concat_cmd, kept_takes, needs_normalise, srt
from tools.shorts.model import load_short


@pytest.fixture(autouse=True)
def encoder(monkeypatch):
    monkeypatch.setattr("tools.shorts.remote.h264_encoder", lambda: "libx264")


def test_kept_takes_picks_newest_keep(tmp_path):
    s = load_short(write(tmp_path / "pilot"))
    sd = tmp_path / "work" / "shots" / "S01"
    (sd / "takes").mkdir(parents=True)
    for t in ("t001", "t002", "t003"):
        (sd / "takes" / f"{t}.mp4").write_bytes(b"x")
    (sd / "verdicts.json").write_text(json.dumps({"t001": {"verdict": "keep"}, "t002": {"verdict": "keep"},
                                                  "t003": {"verdict": "reject"}}))
    assert [p.name for p in kept_takes(s, tmp_path / "work")] == ["t002.mp4"]


def test_srt_times_and_text(tmp_path):
    s = load_short(write(tmp_path / "pilot"))
    out = srt(s, ["S01"])
    assert out.startswith("1\n00:00:01,200 --> 00:00:05,000\nWho paid it?")


def test_concat_cmd_with_music_and_subs(tmp_path):
    argv = concat_cmd([tmp_path / "a.mp4"], tmp_path / "list.txt", tmp_path / "m.mp3", tmp_path / "s.srt", tmp_path / "d.mp4")
    joined = " ".join(argv)
    assert argv[0] == "ffmpeg" and "concat" in joined and "subtitles=" in joined and "amix" in joined
    assert "-crf 20" in joined
    assert (tmp_path / "list.txt").read_text() == f"file '{tmp_path / 'a.mp4'}'\n"


def test_concat_cmd_uses_openh264_bitrate(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.shorts.remote.h264_encoder", lambda: "libopenh264")
    joined = " ".join(concat_cmd([tmp_path / "a.mp4"], tmp_path / "l.txt", None, tmp_path / "s.srt", tmp_path / "d.mp4"))
    assert "libopenh264" in joined and "-b:v 4M" in joined and "-crf" not in joined


def test_needs_normalise_decision():
    ok = {"audio": True, "size": (1280, 720), "fps": 24.0}
    assert not needs_normalise([ok, dict(ok)])
    assert needs_normalise([ok, {**ok, "audio": False}])
    assert needs_normalise([ok, {**ok, "size": (1920, 1080)}])
    assert needs_normalise([ok, {**ok, "fps": 30.0}])
