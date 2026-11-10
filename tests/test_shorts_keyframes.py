import asyncio
import json

import pytest
from PIL import Image

from narrator.designs import Design
from tests.test_review_producers import _shorts_world, ctx, png
from tests.test_shorts_model import SHORT, SHOT, write
from tools.review import producers as P
from tools.shorts import keyframes as kf
from tools.shorts.model import Scene, load_short


def D(name, tags="1girl, black hair"):
    return Design(name=name, kind="character", source="t", tags=tags, required=["long hair"], status="approved")


DESIGNS = {"mama-satos-izakaya": Design(name="Izakaya", kind="location", source="t", tags="izakaya", alt_tags="izakaya, night", status="approved"),
           "saeko-kirigaya": D("Saeko"), "rin-kageyama": D("Rin")}
REG = {"start": {"C1": [0.5, 0.1, 0.9, 1.0], "C2": [0.1, 0.1, 0.45, 1.0]}}


def short_with(tmp_path, shot_extra="", scene=True):
    sc = ('\n[scene]\ntime = "late"\nweather = "indoors"\nset = "bar"\nnot_visible = ["rain", "windows"]\n'
          '[wardrobe]\nC1 = "grey coat"\n[locks]\nC2 = "red scarf"\n') if scene else ""
    return load_short(write(tmp_path, SHORT + sc, SHOT.replace("lens = 35.0", "lens = 35.0\n" + shot_extra)))


def test_workflow_has_area_per_character_controlnet_and_negative(tmp_path):
    s = short_with(tmp_path)
    shot = s.shots[0]
    shot.props = {"C1": "cup in left hand"}
    wf = kf.keyframe_workflow(s, shot, DESIGNS, "start", REG, "g.png", 7)
    areas = [n for n in wf.values() if n["class_type"] == "ConditioningSetArea"]
    assert [(a["inputs"]["x"], a["inputs"]["width"]) for a in areas] == [(608, 480), (120, 424)]
    assert all(v % 8 == 0 for a in areas for v in (a["inputs"]["x"], a["inputs"]["y"], a["inputs"]["width"], a["inputs"]["height"]))
    texts = [wf[k]["inputs"]["text"] for k in ("70", "73")]
    assert "grey coat" in texts[0] and "cup in left hand" in texts[0] and "red scarf" in texts[1]
    assert wf["62"]["class_type"] == "ControlNetApplyAdvanced" and wf["61"]["inputs"]["image"] == "g.png"
    assert wf["3"]["inputs"]["positive"] == ["62", 0] and wf["3"]["inputs"]["negative"] == ["62", 1]
    assert wf["62"]["inputs"]["positive"] == ["75", 0]
    neg = wf["7"]["inputs"]["text"]
    assert "rain" in neg and "windows" in neg and "cleavage" in neg and "daylight" not in neg
    assert "Not visible" not in wf["6"]["inputs"]["text"] and "2girls" in wf["6"]["inputs"]["text"]
    assert wf["5"]["inputs"]["width"] == 1216 and wf["3"]["inputs"]["seed"] == 7


def test_workflow_without_regions_is_a_scene(tmp_path):
    s = short_with(tmp_path, scene=False)
    wf = kf.keyframe_workflow(s, s.shots[0], DESIGNS, "start", {}, "g.png", 1)
    assert not [n for n in wf.values() if n["class_type"] == "ConditioningSetArea"]
    assert wf["62"]["inputs"]["positive"] == ["6", 0] and "rain" not in wf["7"]["inputs"]["text"]


def test_needed_keyframes(tmp_path):
    shot = short_with(tmp_path).shots[0]
    assert kf.needed(shot) == ["start"]
    shot.end_frame = True
    assert kf.needed(shot) == ["start", "end"]
    shot.end_frame, shot.at_end = False, {"C1": "x"}
    assert kf.needed(shot) == ["start", "end"]
    shot.mode = "reference"
    assert kf.needed(shot) == []


def test_plan_jobs_choose_and_redo(tmp_path):
    s = short_with(tmp_path / "s")
    work = tmp_path / "w"
    assert kf.plan_jobs(s, work)[1] and kf.plan_jobs(s, work)[0] == []  # no guide: skipped with a note
    shot_dir = work / "shots" / "S01"
    png(shot_dir / "guide" / "start-lineart.png")
    (shot_dir / "guide" / "regions.json").write_text(json.dumps(REG))
    jobs, _ = kf.plan_jobs(s, work, "S01", "both", 2)
    assert [(j[0].name, j[2], j[5]) for j in jobs] == [("start-c01.png", "start", 1), ("start-c02.png", "start", 2)]
    assert jobs[0][4] == REG
    assert kf.plan_jobs(s, work, "S02")[0] == []
    png(work / "shots" / "S01" / "keyframes" / "start-c01.png")
    assert [j[0].name for j in kf.plan_jobs(s, work, seeds=2)[0]] == ["start-c02.png"]
    assert len(kf.plan_jobs(s, work, seeds=2, redo=True)[0]) == 2
    with pytest.raises(ValueError, match="1216x832"):
        kf.choose(work, "S01", "start", 1)  # 64x64 candidate
    with pytest.raises(ValueError, match="no candidate"):
        kf.choose(work, "S01", "start", 9)
    png(shot_dir / "keyframes" / "start-c02.png", (1216, 832))
    assert kf.choose(work, "S01", "start", 2) == shot_dir / "keyframe-start.png"
    assert kf.plan_jobs(s, work)[0] == []  # chosen: nothing to render


def test_render_uploads_unique_guide_seeds_and_survives_failure(tmp_path):
    class Fake:
        def __init__(self): self.uploads, self.runs = [], []
        async def upload_image(self, name, b): self.uploads.append(name); return "in-" + name
        async def run_workflow(self, wf):
            self.runs.append(wf)
            if len(self.runs) == 1:
                raise RuntimeError("boom")
            return b"png"
    s = short_with(tmp_path / "s")
    art = png(tmp_path / "a.png")
    f = Fake()
    jobs = [(tmp_path / f"o{n}.png", s.shots[0], "start", art, REG, n) for n in (1, 3)]
    errs = asyncio.run(kf.render(jobs, f, s, DESIGNS, 10))
    assert len(errs) == 1 and "boom" in errs[0] and (tmp_path / "o3.png").read_bytes() == b"png"
    assert f.uploads[0] == f"key-guide-{s.slug}-S01-start.png" and s.slug
    assert f.runs[0]["3"]["inputs"]["seed"] == 10 and f.runs[1]["3"]["inputs"]["seed"] == 12


def test_producer_candidates_then_chosen_with_compare(tmp_path):
    c = _shorts_world(tmp_path)
    dd = c["design_dir"]
    shot_dir = dd / "shorts" / "pilot" / "shots" / "S01"
    assert P.keyframes(c) == []
    for n in (1, 2):
        png(shot_dir / "keyframes" / f"start-c0{n}.png")
    png(shot_dir / "guide" / "start.png")
    (item,) = P.keyframes(c)
    assert item.id == "key--pilot--s01--start" and item.kind == "keyframe" and item.stage == "pre-production"
    assert len(item.files) == 2 and item.compare[-1]["label"] == "Grey-box"
    png(shot_dir / "keyframe-start.png")
    png(dd / "saeko-kirigaya" / "turnaround.png")
    (item,) = P.keyframes(c)
    assert len(item.files) == 1 and item.files[0].endswith("keyframe-start.jpg")
    assert P.keyframes in P.ALL


def test_subject_not_duplicated_and_boxes_stay_inside(tmp_path):
    s = short_with(tmp_path)
    d = dict(DESIGNS, **{"saeko-kirigaya": D("Saeko", "1boy, short hair")})
    solo = kf.keyframe_workflow(s, s.shots[0], d, "start", {"start": {"C1": [0.97, 0.0, 1.0, 1.0]}}, "g", 1)
    assert "1girl" not in solo["6"]["inputs"]["text"]
    (area,) = [n for n in solo.values() if n["class_type"] == "ConditioningSetArea"]
    assert area["inputs"]["x"] + area["inputs"]["width"] <= 1216 and area["inputs"]["x"] % 8 == 0
    two = kf.keyframe_workflow(s, s.shots[0], DESIGNS, "start", REG, "g", 1)["6"]["inputs"]["text"]
    assert two.count("2girls") == 1 and "1girl" not in two


def test_plan_jobs_skips_shot_without_character_regions(tmp_path):
    s = short_with(tmp_path / "s")
    work = tmp_path / "w"
    png(work / "shots" / "S01" / "guide" / "start-lineart.png")
    (work / "shots" / "S01" / "guide" / "regions.json").write_text(json.dumps({"end": REG["start"]}))
    jobs, notes = kf.plan_jobs(s, work)
    assert jobs == [] and "regions" in notes[0]
