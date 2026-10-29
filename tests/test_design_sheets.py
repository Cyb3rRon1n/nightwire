import io

import pytest
from PIL import Image

from narrator.design_sheets import (
    BASE_SIZE, MOOD_SUFFIXES, SHEET_NEGATIVE_EXTRA, SHEET_STYLE, candidate_prompt, candidate_workflow,
    extract_palette, join_strip, sheet_prompt, sheet_workflow, subject_for,
)
from narrator.designs import Design
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE


def _char(**kw):
    base = dict(name="Rook", kind="character", source="npc:Rook", presentation="feminine",
                tags="black hair, short hair, yellow eyes, black bomber jacket, mechanical left arm, human right hand",
                negative="two mechanical arms")
    base.update(kw)
    return Design(**base)


def _loc():
    return Design(name="Izakaya", kind="location", source="place:Izakaya",
                  tags="izakaya, paper lanterns, noren", alt_tags="indoors, counter, bar stools",
                  props=["paper lanterns", "ramen bowl", "sake bottle"])


def _types(wf):
    return [n["class_type"] for n in wf.values()]


def test_subjects():
    assert subject_for(_char()) == "1girl"
    assert subject_for(_char(presentation="masculine")) == "1boy"
    assert subject_for(_char(presentation=None)) == "1other"
    assert subject_for(_char(source="npc:Hachi", tags="android, robot joints, station attendant uniform")) == "1other"
    assert subject_for(_loc()) == "scenery, no humans"


def test_character_candidate_is_a_turnaround_preview():
    pos, neg = candidate_prompt(_char())
    assert pos.startswith(QUALITY + ", " + SHEET_STYLE + ", character sheet, reference sheet, turnaround")
    assert pos.endswith(", 1girl, black hair, short hair, yellow eyes, black bomber jacket, mechanical left arm, human right hand")
    assert ", text," not in neg and SHEET_NEGATIVE_EXTRA in neg and neg.endswith("two mechanical arms")


def test_location_candidate_uses_the_game_style():
    pos, neg = candidate_prompt(_loc())
    assert pos == ", ".join([QUALITY, STYLE, "scenery, no humans", "izakaya, paper lanterns, noren"])
    assert neg == NEGATIVE


def test_colorguide_focuses_the_signature_chrome():
    pos, _ = sheet_prompt(_char(), "colorguide")
    assert "color guide" in pos and "mechanical left arm focus" in pos


def test_expressions_sheet_tags():
    pos, _ = sheet_prompt(_char(), "expressions")
    assert "expressions, expression chart, multiple views, portrait, upper body" in pos


def test_location_sheets():
    alt, _ = sheet_prompt(_loc(), "alternate")
    assert "indoors, counter, bar stools" in alt and "izakaya, paper lanterns" not in alt
    mood, _ = sheet_prompt(_loc(), "moodkeys", mood=MOOD_SUFFIXES[1])
    assert mood.endswith("rain, wet street")
    props, _ = sheet_prompt(_loc(), "props")
    assert SHEET_STYLE in props and "still life, no humans, object focus, multiple views, white background" in props
    assert "paper lanterns, ramen bowl, sake bottle" in props


def test_unknown_sheet_raises():
    with pytest.raises(ValueError):
        sheet_prompt(_char(), "establishing")
    with pytest.raises(ValueError):
        sheet_prompt(_loc(), "turnaround")


def test_candidate_workflow_is_single_pass_with_the_19a_look():
    wf = candidate_workflow("P", "N", 7)
    t = _types(wf)
    assert t.count("KSampler") == 1 and "UpscaleModelLoader" not in t
    nodes = {n["class_type"]: n["inputs"] for n in wf.values()}
    assert nodes["CheckpointLoaderSimple"]["ckpt_name"] == "NoobAI-XL-Vpred-v1.0.safetensors"
    assert nodes["LoraLoader"]["lora_name"] == "Smooth_Booster_v3.safetensors"
    assert nodes["ModelSamplingDiscrete"]["sampling"] == "v_prediction" and nodes["RescaleCFG"]["multiplier"] == 0.6
    assert (nodes["EmptyLatentImage"]["width"], nodes["EmptyLatentImage"]["height"]) == BASE_SIZE
    assert nodes["KSampler"]["seed"] == 7 and nodes["KSampler"]["cfg"] == 4.5


def test_sheet_workflow_has_refine_and_final_upscale():
    wf = sheet_workflow("P", "N", 7)
    t = _types(wf)
    assert t.count("KSampler") == 2 and t.count("ImageUpscaleWithModel") == 2
    refine = [n["inputs"] for n in wf.values() if n["class_type"] == "KSampler" and n["inputs"]["denoise"] < 1][0]
    assert refine["denoise"] == 0.35 and refine["steps"] == 20
    scale = [n["inputs"] for n in wf.values() if n["class_type"] == "ImageScaleBy"][0]
    assert scale["scale_by"] == 0.75
    save = [n["inputs"] for n in wf.values() if n["class_type"] == "SaveImage"][0]
    final = wf[save["images"][0]]
    assert final["class_type"] == "ImageUpscaleWithModel"


def test_sheet_workflow_low_res_is_single_pass():
    assert _types(sheet_workflow("P", "N", 7, high_res=False)).count("KSampler") == 1


def _png(color, size=(1216, 832)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_join_strip():
    out = Image.open(io.BytesIO(join_strip([_png("red"), _png("green"), _png("blue")])))
    assert out.size == (3648, 832)
    assert out.getpixel((10, 10)) == (255, 0, 0) and out.getpixel((1216 + 10, 10))[1] > 100


def test_extract_palette():
    img = Image.new("RGB", (100, 100), (255, 204, 0))
    img.paste((17, 17, 17), (0, 0, 100, 30))
    buf = io.BytesIO(); img.save(buf, "PNG")
    palette = extract_palette(buf.getvalue(), n=2)
    assert palette[0] == "#ffcc00" and palette[1] == "#111111"
