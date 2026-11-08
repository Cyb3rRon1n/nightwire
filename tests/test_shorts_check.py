from pathlib import Path

from tools.design_check import scene_people
from tools.shorts.check import extract_cmd, frame_names


def test_frame_names_follow_design_check_naming():
    names = frame_names(["saeko-kirigaya", "rin-kageyama"], "S01", "t001", 2)
    assert names == ["pair--saeko-kirigaya--rin-kageyama--S01-t001-f1.png",
                     "pair--saeko-kirigaya--rin-kageyama--S01-t001-f2.png"]
    assert scene_people(names[0]) == ["saeko-kirigaya", "rin-kageyama"]
    assert scene_people(frame_names(["saeko-kirigaya"], "S01", "t001", 1)[0]) == ["saeko-kirigaya"]


def test_extract_cmd_samples_evenly():
    argv = extract_cmd(Path("t.mp4"), Path("out/f%d.png"), 4, 8.0)
    assert argv[0] == "ffmpeg" and "fps=0.5" in " ".join(argv)
