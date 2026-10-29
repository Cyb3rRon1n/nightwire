import io

import pytest
from PIL import Image

from narrator.design_sheets import (
    BASE_SIZE, CHARACTER_MATURE, CHARACTER_SHEET_STYLE, MOOD_SUFFIXES, SHEET_NEGATIVE_EXTRA, SHEET_STYLE, candidate_prompt, candidate_workflow,
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
    assert pos.startswith(QUALITY.replace("safe", "sensitive") + ", " + CHARACTER_SHEET_STYLE + ", " + CHARACTER_MATURE
                          + ", character sheet, reference sheet, turnaround")
    assert "safe" not in pos.split(", ") and "sensitive" in pos.split(", ")
    assert SHEET_STYLE not in pos
    assert pos.endswith(", 1girl, black hair, short hair, yellow eyes, black bomber jacket, mechanical left arm, human right hand")
    assert ", text," not in neg and SHEET_NEGATIVE_EXTRA in neg and neg.endswith("two mechanical arms")
    assert "nude" in neg and "loli" in neg


def test_location_candidate_uses_the_game_style():
    pos, neg = candidate_prompt(_loc())
    assert pos == ", ".join([QUALITY, STYLE, "scenery, no humans", "izakaya, paper lanterns, noren"])
    assert neg == NEGATIVE
    est, _ = sheet_prompt(_loc(), "establishing")
    assert "safe" in est.split(", ") and "sensitive" not in est


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
    props, props_neg = sheet_prompt(_loc(), "props")
    assert "nude" not in props_neg
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


def test_moodkeys_night_tag_only_for_the_night_mood():
    for mood in MOOD_SUFFIXES:
        pos, _ = sheet_prompt(_loc(), "moodkeys", mood=mood)
        assert ("night" in pos.split(", ")) == (mood == "night, neon lights"), mood
        assert pos.endswith(mood)


def test_establishing_keeps_the_night_tag():
    pos, _ = sheet_prompt(_loc(), "establishing")
    assert "night" in pos.split(", ")


def _white_sheet():
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    img.paste((200, 30, 30), (0, 0, 20, 100))
    img.paste((30, 30, 200), (20, 0, 30, 100))
    buf = io.BytesIO(); img.save(buf, "PNG")
    return buf.getvalue()


def test_extract_palette_skips_white_background():
    palette = extract_palette(_white_sheet(), n=2)
    assert len(palette) == 2 and "#ffffff" not in palette
    assert palette[0].startswith("#c8") and palette[1].startswith("#1e")


def test_extract_palette_keeps_white_when_asked():
    assert "#ffffff" in extract_palette(_white_sheet(), n=3, skip_background=False)
