"""Character shots: wardrobe states, v2 sheet refs, plate + draft board, approvals."""

import pytest
from PIL import Image

from narrator.designs import WardrobeState
from test_shorts_model import PLANNED, SHORT, designs, write
from tools.review import producers as P
from tools.shorts import preflight
from tools.shorts.approve import board_id
from tools.shorts.model import load_short, validate_short
from tools.shorts.prompt import CHARACTER_SHEETS, build_prompt, expected_refs, trim_refs

REF = PLANNED.replace("lens = 35.0", 'lens = 35.0\nmode = "reference"\nplate = "door"')
WARD = SHORT + '\n[wardrobe]\nC1 = "work"\nC2 = "red coat with a hood"\n'
KEEP = {"verdict": "keep"}


def state_designs():
    d = designs()
    d["saeko-kirigaya"].identity = ["X-shaped scar on the right cheek"]
    d["saeko-kirigaya"].wardrobe = {"work": WardrobeState(text="cropped navy jacket", tags="jacket"),
                                    "offduty": WardrobeState(text="long coat", tags="coat")}
    return d


def short_(tmp_path, short=WARD, shot=REF):
    return load_short(write(tmp_path / "pilot", short=short, shot=shot))


def png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(path)
    return path


def v2(dd, slug="saeko-kirigaya", state="work"):
    for x in ("turnaround", "portrait", "expressions", "props"):
        png(dd / slug / "wardrobe" / state / f"{x}.png")
    return dd / slug / "wardrobe" / state


def test_state_name_resolves_and_unknown_state_is_an_error(tmp_path):
    s = short_(tmp_path)
    assert validate_short(s, state_designs()) == []  # "work" is a state; the C2 free text has spaces
    for text in ("formal", "a long grey coat"):  # with states, only a state name is allowed
        bad = short_(tmp_path / text[:3], short=SHORT + f'\n[wardrobe]\nC1 = "{text}"\n')
        assert any("C1" in p and "not a wardrobe state" in p for p in validate_short(bad, state_designs()))
    free = short_(tmp_path / "f", short=SHORT + '\n[wardrobe]\nC1 = "formal"\n')
    assert validate_short(free, designs()) == []  # no states on the design: any free text


def test_prompt_uses_state_text_and_identity(tmp_path):
    p = build_prompt(short_(tmp_path), short_(tmp_path / "x").shots[0], state_designs())
    assert "cropped navy jacket" in p and "X-shaped scar on the right cheek" in p and "red coat with a hood" in p
    assert "C1 Saeko Kirigaya: work" not in p


def test_v2_refs_then_v1_fallback_with_warning(tmp_path):
    s, dd, sd = short_(tmp_path), tmp_path / "dd", tmp_path / "dd" / "sd"
    warns = []
    refs = dict(expected_refs(s, dd, sd, designs=state_designs(), shot=s.shots[0], warnings=warns))
    assert refs["C1_turnaround.png"] == dd / "saeko-kirigaya" / "turnaround.png" and "C1 work" in warns[0]
    folder = v2(dd)
    warns.clear()
    refs = dict(expected_refs(s, dd, sd, designs=state_designs(), shot=s.shots[0], warnings=warns))
    assert refs["C1_portrait.png"] == folder / "portrait.png" and not warns
    labels = list(refs)
    assert labels[-2:] == ["place.png", "start_frame.png"] and refs["start_frame.png"] == sd / "board-start.png"
    png(sd / "board-end.png")
    assert list(dict(expected_refs(s, dd, sd, designs=state_designs(), shot=s.shots[0])))[-1] == "end_frame.png"


def test_only_cast_in_frame_get_sheets(tmp_path):
    s = short_(tmp_path, shot=REF.replace('C2 = "screen-left, facing camera"\n', ""))
    labels = [l for l, _ in expected_refs(s, tmp_path, tmp_path, shot=s.shots[0])]
    assert not any(l.startswith("C2_") for l in labels) and "C1_turnaround.png" in labels


def test_trim_drops_expressions_then_props_unless_featured_then_portrait(tmp_path):
    s = short_(tmp_path)
    shot = s.shots[0]
    refs = [(f"{c}_{f}", tmp_path) for c in ("C1", "C2") for f in CHARACTER_SHEETS] + \
           [("place.png", tmp_path), ("start_frame.png", tmp_path), ("end_frame.png", tmp_path)]
    names = [l for l, _ in trim_refs(refs, 9, shot)]
    assert len(names) == 9 and "end_frame.png" not in names and "C1_expressions.png" in names and "C2_expressions.png" not in names
    shot.props = {"C1": "cup"}
    names = [l for l, _ in trim_refs(refs, 6, shot)]
    assert "C1_props.png" in names and "C2_props.png" not in names and not any("expressions" in n for n in names)
    refs = [r for r in refs if r[0] != "C2_props.png" and "expressions" not in r[0]]
    names = [l for l, _ in trim_refs(refs, 8, shot)]
    assert len(names) == 8 and "C2_portrait.png" in names  # portraits go last
    names = [l for l, _ in trim_refs(refs, 5, shot)]
    assert len(names) == 5 and "C1_props.png" in names and not any("portrait" in n for n in names)


def _approvals(images):
    return {"images": images, "SCENE": {}}


def test_character_shot_needs_board_and_v2_set_approved(tmp_path):
    from tools.review.producers import sheet_set_id
    s, dd = short_(tmp_path), tmp_path / "dd"
    sd = dd / "shorts" / s.slug / "shots" / "S01"
    run = lambda images: preflight.package(s, s.shots[0], None, {}, sd, _approvals(images), dd, state_designs())  # noqa: E731
    p = run({})
    assert "no draft board (board-start.png)" in p and "C1 work: v2 sheet set missing" in p
    folder, board = v2(dd), png(sd / "board-start.png")
    p = run({})
    assert "draft board not approved" in p and "C1 work: v2 sheet set not approved" in p
    p = run({board_id(s.slug, "S01", board): KEEP, sheet_set_id("saeko-kirigaya", "work", folder): KEEP})
    assert not any("board" in x or "sheet set" in x for x in p), p


def test_environment_shot_needs_plate_approved_not_keyframes(tmp_path):
    s = short_(tmp_path, shot=PLANNED.replace("lens = 35.0", 'lens = 35.0\nplate = "door"\nmotion = "steam drifts"')
               .replace("\n[frame]\nC2", "\n[unused]\nC2"))
    shot = s.shots[0]
    shot.frame = {}
    p = preflight.package(s, shot, None, {}, tmp_path, _approvals({}), tmp_path)
    assert not any("keyframe" in x for x in p)


def test_boards_producer_one_item_per_shot_board(tmp_path):
    c = {"design_dir": tmp_path / "dd", "site": tmp_path / "site", "shorts_dir": tmp_path / "script", "designs": designs(),
         "plates_root": tmp_path / "plates"}
    s = load_short(write(tmp_path / "script" / "pilot", shot=REF))
    sd = c["design_dir"] / "shorts" / "pilot" / "shots" / "S01"
    assert P.boards(c) == []
    board = png(sd / "board-start.png")
    (item,) = P.boards(c)
    assert item.id == board_id("pilot", "S01", board) and item.kind == "board" and item.stage == "pre-production"
    assert P.boards in P.ALL


def test_environment_shot_skips_cast_fields(tmp_path):
    sh = short_(tmp_path, shot=PLANNED.replace("lens = 35.0", 'lens = 35.0\nplate = "door"')).shots[0]
    sh.frame, sh.at_start, sh.at_end = {}, {}, {}
    assert preflight.required(sh) == []
    sh.plate = ""
    assert "missing frame" in preflight.required(sh)


def test_i2v_shot_with_cast_in_frame_is_a_problem(tmp_path):
    s = short_(tmp_path, shot=REF.replace('mode = "reference"', 'mode = "i2v"'))
    p = preflight.package(s, s.shots[0], None, {}, tmp_path, _approvals({}), tmp_path, state_designs())
    assert any("i2v is for empty-room shots" in x for x in p) and "no draft board (board-start.png)" in p


def test_board_id_covers_end_board_and_plan_item_shows_it(tmp_path):
    sd = tmp_path / "sd"
    start = png(sd / "board-start.png")
    a = board_id("pilot", "S01", start)
    Image.new("RGB", (8, 8), "red").save(sd / "board-end.png")
    b = board_id("pilot", "S01", start)
    assert a != b
    Image.new("RGB", (8, 8), "blue").save(sd / "board-end.png")
    assert board_id("pilot", "S01", start) not in (a, b)
    s = short_(tmp_path)
    run = lambda images: preflight.package(s, s.shots[0], None, {}, sd, _approvals(images), tmp_path, state_designs())  # noqa: E731
    assert "draft board not approved" in run({b: KEEP})  # keep on the old end board
    assert "draft board not approved" not in run({board_id(s.slug, "S01", start): KEEP})


def test_wardrobe_line_lists_only_cast_in_frame(tmp_path):
    s = short_(tmp_path, shot=REF.replace('C2 = "screen-left, facing camera"\n', ""))
    p = build_prompt(s, s.shots[0], state_designs())
    assert "cropped navy jacket" in p and "red coat with a hood" not in p


def test_frame_cid_not_in_cast_is_a_validation_error(tmp_path):
    s = short_(tmp_path, shot=REF.replace('C2 = "screen-left', 'C9 = "screen-left'))
    assert any("unknown cast id C9" in p for p in validate_short(s, state_designs()))


def test_bundle_refuses_character_shot_that_fails_preflight(tmp_path, monkeypatch, capsys):
    from test_shorts_cli import PACKAGED, setup
    from tools.shorts.__main__ import main
    setup(tmp_path, monkeypatch, shot=PACKAGED)
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: {})  # nothing approved
    assert main(["bundle", "pilot", "S01"]) == 1
    assert "no bundle written" in capsys.readouterr().err
