import pytest

from test_shorts_model import SHOT, designs, write
from tools.shorts.model import load_short
from tools.shorts.prompt import build_prompt, layers, position_problems, ref_files


def short_and_shot(tmp_path):
    s = load_short(write(tmp_path / "pilot"))
    return s, s.shots[0]


def test_layers_state_each_fact_once(tmp_path):
    s, shot = short_and_shot(tmp_path)
    L = layers(s, shot, designs())
    assert "grey-box" in L["L1"] and shot.summary in L["L1"]
    assert "C1 = Saeko Kirigaya" in L["L2"] and "C2 = Rin Kageyama" in L["L2"]
    assert s.style in L["L3"]
    assert "C2: guarded, pretending not to care" in L["L4"]
    assert "0.0-2.5s" in L["L5"] and "Who paid it?" in L["L5"]
    assert "block on \"Who\"" in L["L5"]


def test_build_prompt_joins_layers_in_order(tmp_path):
    s, shot = short_and_shot(tmp_path)
    p = build_prompt(s, shot, designs())
    assert p.index("C1 = Saeko") < p.index(s.style) < p.index("Who paid it?")


@pytest.mark.parametrize("text", ["sits on the left", "behind the counter", "next to C1", "in front of the door"])
def test_position_words_in_state_are_rejected(text):
    assert position_problems({"L1": "", "L2": "C1 = Saeko", "L3": "", "L4": f"C1: tired, {text}", "L5": "C1 left"})


def test_position_words_in_timecodes_are_fine():
    assert position_problems({"L1": "", "L2": "C1 = Saeko", "L3": "", "L4": "C1: tired", "L5": "C2 frame right"}) == []


def test_build_prompt_raises_on_position_words(tmp_path):
    s, shot = short_and_shot(tmp_path)
    shot.state["C1"] = "tired, sitting left of the door"
    with pytest.raises(ValueError, match="L4"):
        build_prompt(s, shot, designs())


def test_ref_files_lists_existing_refs_in_order(tmp_path):
    s, shot = short_and_shot(tmp_path)
    dd = tmp_path / "design-data"
    for slug, files in {"saeko-kirigaya": ["turnaround.png", "expressions.png"], "rin-kageyama": ["turnaround.png"],
                        "mama-satos-izakaya": ["play.png"]}.items():
        (dd / slug).mkdir(parents=True)
        for f in files:
            (dd / slug / f).write_bytes(b"x")
    shot_dir = tmp_path / "S01"
    shot_dir.mkdir()
    (shot_dir / "greybox.mp4").write_bytes(b"x")
    labels = [label for label, _ in ref_files(s, dd, shot_dir)]
    assert labels == ["C1_turnaround.png", "C1_expressions.png", "C2_turnaround.png", "place.png", "greybox.mp4"]


def test_l5_times_are_relative_to_shot_start(tmp_path):
    shifted = (SHOT.replace("start = 0.0", "start = 8.0").replace("end = 5.0", "end = 13.0")
               .replace("t = [0.0, 2.5]", "t = [8.0, 10.5]").replace("t = [1.0, 3.5]", "t = [9.0, 11.5]")
               .replace("t = 1.2", "t = 9.2").replace("t = 0.0,", "t = 0.0,"))
    s = load_short(write(tmp_path / "pilot", shot=shifted))
    L5 = layers(s, s.shots[0], designs())["L5"]
    assert "0.0-2.5s" in L5 and "1.0-3.5s" in L5 and "1.2s C2 says" in L5
    assert "8.0" not in L5 and "9.2" not in L5


def test_still_replaces_place_and_l1_says_so(tmp_path):
    from test_shorts_model import designs, write
    from tools.shorts.model import load_short
    from tools.shorts.prompt import build_prompt, ref_files
    s = load_short(write(tmp_path / "script"))
    dd = tmp_path / "dd"
    (dd / "mama-satos-izakaya").mkdir(parents=True)
    (dd / "mama-satos-izakaya" / "play.png").write_bytes(b"p")
    shot_dir = dd / "shorts" / s.slug / "shots" / "S01"
    shot_dir.mkdir(parents=True)
    assert "place.png" in [l for l, _ in ref_files(s, dd, shot_dir)]
    (shot_dir / "still.png").write_bytes(b"s")
    labels = [l for l, _ in ref_files(s, dd, shot_dir)]
    assert "start_frame.png" in labels and "place.png" not in labels
    assert "start_frame.png" in build_prompt(s, s.shots[0], designs(), has_still=True)
    assert "start_frame.png" not in build_prompt(s, s.shots[0], designs())
