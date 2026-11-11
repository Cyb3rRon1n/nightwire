from tools import comfy_presets as cp
from tools.imagegen import build


def test_presets_are_night_and_e_look_only():
    assert "scene day" not in cp.PRESETS and "painterly" not in cp.PRESETS
    for p in cp.PRESETS.values():
        assert not p.get("options", {}).get("day") and not p.get("raw")


def test_scene_presets_use_the_medium_dark_recipe():
    p = cp.PRESETS["scene"]
    wf = build(p["prompt"], p["kind"], False, "", "base", 1, **p["options"])
    assert "muted colors" in wf["6"]["inputs"]["text"] and wf["3"]["inputs"]["cfg"] == 3.5


def test_location_preset_matches_the_plate_recipe():
    wf = cp.location_workflow()
    assert wf["3"]["inputs"]["cfg"] == 3.5 and wf["34"]["inputs"]["denoise"] == 0.35
    assert "photorealistic" in wf["7"]["inputs"]["text"] and "40" not in wf
