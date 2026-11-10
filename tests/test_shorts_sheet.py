import json

from test_shorts_model import SHORT, SHOT, designs, write
from tools.shorts import sheet
from tools.shorts.model import load_short
from tools.shorts.preflight import Report


def test_collect_and_build(tmp_path):
    s = load_short(write(tmp_path / "script", short=SHORT.replace('budget_usd = 25.0', 'budget_usd = 25.0\nline_rule = "C1 screen-right"')))
    dd = tmp_path / "design-data"
    for slug in ("saeko-kirigaya", "rin-kageyama"):
        (dd / slug).mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (64, 64)).save(dd / slug / "turnaround.png")
    (dd / "mama-satos-izakaya").mkdir()
    from PIL import Image
    Image.new("RGB", (64, 64)).save(dd / "mama-satos-izakaya" / "play.png")
    work = dd / "shorts" / s.slug
    (work / "shots" / "S01").mkdir(parents=True)
    (work / "shots" / "S01" / "greybox.mp4").write_bytes(b"g")
    (work / "costs.json").write_text(json.dumps([
        {"shot": "S01", "take": "req-1", "model": "m", "cost": 1.0, "note": "override: owner said go"},
        {"shot": "S01", "take": "req-2", "model": "m", "cost": 0.5}, {"shot": "S02", "take": "req-3", "model": "m", "cost": 0.5, "note": "x"}]))
    ref = dd / "saeko-kirigaya" / "turnaround.png"
    plans = {"S01": (Report(problems=["missing size"], warnings=["w"]), "PROMPT TEXT", [("C1_turnaround.png", ref)])}
    data = sheet.collect(s, designs(), dd, work, "seedance-2.0-fast", plans)
    row = data["shots"][0]
    assert row["id"] == "S01" and row["problems"] == ["missing size"] and row["prompt"] == "PROMPT TEXT"
    assert row["image_id"].startswith(f"plan--{s.slug}--s01--") and row["cost"] > 0
    assert row["overrides"] == ["override: owner said go"] and data["spent"] == 2.0
    assert data["line_rule"] == "C1 screen-right" and data["lines"][0]["who"] == "C2"
    site = sheet.build(data, dd, work, tmp_path / "site")
    assert (site / "sheet" / "index.html").read_text().count('content="0; url=../"') == 1
    assert (site / "index.html").exists() and json.loads((site / "sheet.json").read_text())["slug"] == s.slug
    assert (site / "cast" / "saeko-kirigaya-turnaround.jpg").exists()
    html = (site / "index.html").read_text()
    assert "/review/?project=" in html and "PUT" not in html and "innerHTML" not in html and "alert(" not in html and "Paid without approval: " in html


def _stage_short(tmp_path):
    from test_shorts_model import SHORT, SHOT, write
    scene = '\n[scene]\ntime = "late night"\nweather = "indoors"\nset = "a bar"\n[wardrobe]\nC1 = "coat"\n'
    return load_short(write(tmp_path / "script", SHORT + scene, SHOT.replace("lens = 35.0", 'lens = 35.0\nplate = "toward-door"')))


def _plates():
    from tools.shorts.plates import Plate
    return {"toward-door": Plate("toward-door", "v", "")}


def test_stages_bible_waiting_locks_everything_after(tmp_path):
    s = _stage_short(tmp_path)
    out = sheet.stages(s, [{"id": "S01", "fp": "x"}], _plates(), {"images": {}}, tmp_path / "w")
    assert [o["name"] for o in out] == ["Bible", "Plates", "Keyframes", "Shots", "Takes", "Cut"]
    assert out[0]["status"] == "waiting" and {o["status"] for o in out[1:]} == {"locked"}


def test_stages_bible_and_plates_approved_keyframes_waiting(tmp_path, monkeypatch):
    from tools.shorts import keyframes
    from tools.shorts.approve import scene_fp
    from tools.shorts.plates import plate_id
    s = _stage_short(tmp_path)
    s.shots[0].mode = "i2v"
    ap = {"SCENE": {scene_fp(s): {"verdict": "keep"}}, "images": {plate_id(s.place, "toward-door"): {"verdict": "keep"}}}
    out = sheet.stages(s, [{"id": "S01", "fp": "x"}], _plates(), ap, tmp_path / "w")
    assert [o["status"] for o in out] == ["approved", "approved", "waiting", "locked", "locked", "locked"]
    # keyframe drawn and kept -> keyframes approved, shots waiting
    kf = keyframes.chosen_path(tmp_path / "w", "S01", "start")
    kf.parent.mkdir(parents=True)
    kf.write_bytes(b"x")
    for w in keyframes.needed(s.shots[0]):
        ap["images"][f"key--{s.slug}--s01--{w}"] = {"verdict": "keep"}
        keyframes.chosen_path(tmp_path / "w", "S01", w).write_bytes(b"x")
    out = sheet.stages(s, [{"id": "S01", "fp": "x"}], _plates(), ap, tmp_path / "w")
    assert [o["status"] for o in out[2:4]] == ["approved", "waiting"]
    ap["S01"] = {"x": {"verdict": "keep"}}
    (tmp_path / "w" / "shots" / "S01" / "verdicts.json").write_text('{"t1": {"verdict": "keep"}}')
    (tmp_path / "w" / "draft.mp4").write_bytes(b"v")
    ap["images"][sheet.cut_id(s.slug, tmp_path / "w" / "draft.mp4")] = {"verdict": "keep"}
    assert {o["status"] for o in sheet.stages(s, [{"id": "S01", "fp": "x"}], _plates(), ap, tmp_path / "w")} == {"approved"}
    (tmp_path / "w" / "draft.mp4").write_bytes(b"new cut")  # a new cut needs its own approval
    assert sheet.stages(s, [{"id": "S01", "fp": "x"}], _plates(), ap, tmp_path / "w")[-1]["status"] == "waiting"
