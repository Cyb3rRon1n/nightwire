import io

import pytest
from PIL import Image

from narrator.design_sheets import (
    EXPRESSIONS, expression_grid, expression_prompts, BASE_SIZE, CHARACTER_MATURE, CHARACTER_SHEET_STYLE, MOOD_SUFFIXES, SHEET_NEGATIVE_EXTRA, SHEET_STYLE, candidate_prompt, candidate_workflow,
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
    assert ", text," not in neg and SHEET_NEGATIVE_EXTRA in neg and "two mechanical arms" in neg
    assert "nude" in neg and "loli" in neg


def test_location_candidate_uses_the_game_style():
    pos, neg = candidate_prompt(_loc())
    assert pos.startswith(", ".join([QUALITY, STYLE, "scenery, no humans", "izakaya, paper lanterns, noren"]))
    assert "muted colors" in pos  # the owner's medium dark look
    assert neg.startswith(NEGATIVE) and "people" in neg
    est, _ = sheet_prompt(_loc(), "establishing")
    assert "safe" in est.split(", ") and "sensitive" not in est


def test_colour_guide_is_built_from_the_turnaround_not_rendered():
    with pytest.raises(ValueError):
        sheet_prompt(_char(), "colorguide")
    im = Image.new("RGB", (400, 200), (128, 128, 128))
    im.paste((10, 200, 10), (50, 50, 70, 70))  # the head
    buf = io.BytesIO(); im.save(buf, "PNG")
    got = Image.open(io.BytesIO(ds.colour_guide(buf.getvalue(), ["#ff0000", "#0000ff"], head=(50, 50, 70, 70)))).convert("RGB")
    assert got.size == (500, 200)
    assert got.getpixel((60, 60)) == (10, 200, 10)  # the turnaround itself, untouched
    assert got.getpixel((450, 50))[1] > 150  # close-up of the head
    assert got.getpixel((450, 120)) == (255, 0, 0) and got.getpixel((450, 180)) == (0, 0, 255)


def test_extract_palette_skips_the_grey_and_near_duplicates():
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    img.paste((20, 20, 20), (0, 0, 40, 100))
    img.paste((26, 26, 26), (40, 0, 60, 100))
    img.paste((240, 240, 240), (60, 0, 80, 100))
    buf = io.BytesIO(); img.save(buf, "PNG")
    palette = extract_palette(buf.getvalue(), n=4)
    assert len(palette) == 2 and palette[0].startswith("#14") and palette[1].startswith("#f0")


def _ayame():
    return Design("Ayame", "character", "new:x", "red hair, confident smirk, scar through eyebrow, silk shirt, cigarette, high heels",
                  presentation="feminine", held=["cigarette"], required=["purple eyes"], negative="plump")


def test_expression_panels_show_only_the_face_and_one_mood():
    panels = expression_prompts(_ayame())
    assert [p[0] for p in panels] == [e[0] for e in EXPRESSIONS]
    for label, pos, neg in panels:
        assert "red hair" in pos and "scar through eyebrow" in pos and "silk shirt" in pos
        assert "cigarette" not in pos and "high heels" not in pos and "confident smirk" not in pos
        assert "multiple views" not in pos and "tattoo" not in pos
        assert all(w in neg for w in ("cigarette", "holding", "floating object", "fangs", "plump", "nude", "child"))
    assert "angry" in panels[2][1] and "smirk" in panels[5][1]
    assert panels[0][1].index("purple eyes") < panels[0][1].index("red hair") and "face focus" in panels[0][1]


def test_expression_panels_keep_a_fang_that_is_canon():
    d = Design("Kenji", "character", "x", "black hair, fang, grin", presentation="masculine")
    pos, neg = expression_prompts(d)[0][1:]
    assert "fang" in pos and "fang," not in neg and "fangs" not in neg


def test_expression_grid_has_a_fixed_layout():
    from PIL import Image
    panels = [(str(i), _png_bytes()) for i in range(6)]
    assert Image.open(io.BytesIO(expression_grid(panels))).size == (3 * 64, 2 * 48)


def _png_bytes():
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (64, 48), "red").save(out, "PNG")
    return out.getvalue()


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


def test_sheet_pose_steers_first_pass_only():
    wf = sheet_workflow("P", "N", 7, pose="skeleton.png")
    assert wf["51"]["inputs"]["image"] == "skeleton.png"
    assert wf["3"]["inputs"]["positive"] == ["52", 0] and wf["3"]["inputs"]["negative"] == ["52", 1]
    assert wf["34"]["inputs"]["positive"] == ["6", 0]
    assert "50" not in sheet_workflow("P", "N", 7)


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


def test_extract_palette_keeps_a_small_saturated_accent():
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    img.paste((20, 20, 20), (0, 0, 40, 100))
    img.paste((230, 230, 230), (40, 0, 70, 100))
    img.paste((70, 70, 75), (70, 0, 90, 100))
    img.paste((240, 20, 150), (90, 0, 93, 100))
    buf = io.BytesIO(); img.save(buf, "PNG")
    assert any(c.startswith("#f0") for c in extract_palette(buf.getvalue(), n=3))


def test_extract_palette_keeps_white_clothes():
    assert "#ffffff" in extract_palette(_white_sheet(), n=3)


def test_sheets_carry_the_record_and_no_generic_marks():
    d = Design(name="A", kind="character", source="x", tags="red hair, suit", required=["purple eyes", "red hair"])
    pos, neg = sheet_prompt(d, "turnaround")
    assert pos.count("red hair") == 1 and "purple eyes" in pos
    assert "tattoo" not in pos and "piercing" not in pos and "floating object" in neg



from narrator import design_sheets as ds  # noqa: E402


def _portrait_design():
    from narrator.designs import load_designs
    from tools.design_studio import DESIGNS_DIR
    return load_designs(DESIGNS_DIR)["mei-lan"]


def test_portrait_uses_the_scene_look_with_the_character_and_stays_adult():
    from narrator.image_prompt import STYLE
    d = _portrait_design()
    pos, neg = ds.portrait_prompt(d)
    assert STYLE in pos and "portrait" in pos and "adult" in pos
    assert all(t in pos for t in d.required)
    assert all(h not in pos for h in d.held)
    assert "child" in neg and "nude" in neg


def test_portrait_allows_its_city_background_and_guards_the_skin():
    pos, neg = ds.portrait_prompt(_portrait_design())
    assert "scenery" not in neg and "simple background" not in neg
    assert "blue skin" in neg and "realistic" in neg


def test_portrait_is_a_character_sheet_at_expression_size():
    d = _portrait_design()
    assert "portrait" in ds.CHARACTER_SHEETS
    assert ds.sheet_prompt(d, "portrait") == ds.portrait_prompt(d)
    wf = ds.sheet_workflow(*ds.portrait_prompt(d), 1, size=ds.EXPRESSION_SIZE)
    assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == ds.EXPRESSION_SIZE
    assert wf["9"]["inputs"]["images"] == ["40", 0]  # the full-quality path, not a draft


def test_expressions_use_the_same_look_as_the_portrait():
    from narrator.image_prompt import STYLE
    d = _portrait_design()
    for _, pos, neg in ds.expression_prompts(d):
        assert STYLE in pos and "defined jawline" not in pos
        assert "scenery" not in neg and "simple background" not in neg and "blue skin" in neg


def test_turnaround_holds_the_plain_grey_look():
    pos, neg = ds.sheet_prompt(_portrait_design(), "turnaround")
    assert "(grey background:1.3)" in pos and "gritty" not in pos and "rim light" not in pos
    assert "black background" in neg and "extra heads" in neg and "simple background" not in neg


def test_ai_characters_get_restrained_expressions():
    ai = Design("Hachi", "character", "x", "android, blank eyes", presentation="feminine")
    panels = ds.expression_prompts(ai)
    assert [p[0] for p in panels] == [e[0] for e in ds.AI_EXPRESSIONS] and len(panels) == len(EXPRESSIONS)
    assert all("angry" not in p[1] and "expressionless" in p[1] for p in panels)
    assert [p[0] for p in expression_prompts(_ayame())] == [e[0] for e in EXPRESSIONS]


def test_flatten_background_paints_what_the_segmenter_calls_backdrop(monkeypatch):
    import sys, types
    import numpy as np
    from PIL import Image
    mask = np.zeros((100, 100), dtype=float)
    mask[20:80, 20:80] = 1.0
    mask[0, 0] = 0.5  # unsure: half way once firmed up
    mask[50, 5] = 0.2  # barely there: counts as backdrop
    fake = types.ModuleType("imgutils.segment")
    fake.segment_rgba_with_isnetis = lambda im: (mask, im)
    monkeypatch.setitem(sys.modules, "imgutils", types.ModuleType("imgutils"))
    monkeypatch.setitem(sys.modules, "imgutils.segment", fake)
    out = io.BytesIO()
    Image.new("RGB", (100, 100), (20, 20, 20)).save(out, "PNG")
    got = Image.open(io.BytesIO(ds.flatten_background(out.getvalue()))).convert("RGB")
    assert got.getpixel((50, 50)) == (20, 20, 20)
    assert got.getpixel((5, 50)) == (128, 128, 128)
    assert 60 < got.getpixel((0, 0))[0] < 90


def _turnaround(height: int) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (900, 600), (128, 128, 128))
    d = ImageDraw.Draw(im)
    d.rectangle((50, 600 - height, 150, 599), fill=(10, 10, 10))  # front view
    d.rectangle((500, 100, 600, 599), fill=(10, 10, 10))  # a later view, must be ignored
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def test_front_figure_takes_only_the_first_view():
    from narrator.design_sheets import front_figure
    assert front_figure(_turnaround(300)).size == (101, 300)


def test_height_lineup_is_to_scale_on_one_ground_line():
    import numpy as np
    from PIL import Image
    from narrator.design_sheets import height_lineup
    png = height_lineup([("Short", 150, _turnaround(300)), ("Tall", 200, _turnaround(300))], px_per_cm=2)
    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    dark = a.sum(axis=2) < 60
    heights = [int(dark[:, x].sum()) for x in np.where(dark.any(axis=0))[0]]
    assert max(heights) == 400 and min(heights) == 300  # tallest first, 2 px per cm
    rows = np.where(dark.any(axis=1))[0]
    assert (rows.max() - rows.min() + 1) == 400  # both stand on the same line


def test_natural_scene_starts_from_the_empty_location():
    from narrator.design_sheets import natural_scene_workflow
    wf = natural_scene_workflow("P", "N", 7, "ref.png", "room.png")
    assert "5" not in wf and wf["70"]["inputs"]["image"] == "room.png"
    assert wf["3"]["inputs"]["latent_image"] == ["71", 0] and wf["3"]["inputs"]["denoise"] == 0.8
    assert (wf["63"]["inputs"]["weight"], wf["63"]["inputs"]["start_at"], wf["63"]["inputs"]["end_at"]) == (0.7, 0.35, 0.75)
    assert "ControlNetApplyAdvanced" not in _types(wf)


def test_natural_scene_without_a_location_starts_empty():
    from narrator.design_sheets import natural_scene_workflow
    wf = natural_scene_workflow("P", "N", 7, "ref.png")
    assert "5" in wf and "70" not in wf


def test_scene_workflow_uses_pose_and_timed_reference_and_stops_before_upscale():
    from narrator.design_sheets import scene_workflow
    wf = scene_workflow("P", "N", 7, "pose.png", "ref.png")
    assert wf["51"]["inputs"]["image"] == "pose.png" and wf["62"]["inputs"]["image"] == "ref.png"
    assert (wf["63"]["inputs"]["start_at"], wf["63"]["inputs"]["end_at"]) == (0.2, 0.5)
    assert wf["3"]["inputs"]["model"] == ["63", 0] == wf["34"]["inputs"]["model"]
    assert wf["3"]["inputs"]["cfg"] == 3.5 and wf["9"]["inputs"]["images"] == ["35", 0] and "40" not in wf


def test_height_pose_scales_figure_and_keeps_feet_on_the_ground_line():
    import numpy as np
    from narrator.design_sheets import SCENE_SIZE, height_pose
    template = Image.new("RGB", (1216, 832), "black")
    for x0, x1 in ((100, 200), (500, 600)):  # front figure, then another view after a gap
        template.paste((255, 255, 255), (x0, 100, x1, 700))
    buf = io.BytesIO(); template.save(buf, "PNG")
    def extent(cm):
        a = np.asarray(Image.open(io.BytesIO(height_pose(buf.getvalue(), cm))).convert("L")) > 30
        rows = np.where(a.any(axis=1))[0]
        return rows[0], rows[-1], a.shape
    t_top, t_feet, shape = extent(195)
    s_top, s_feet, _ = extent(160)
    assert shape == (SCENE_SIZE[1], SCENE_SIZE[0])
    assert abs(t_feet - s_feet) <= 1 and t_top < s_top
    assert abs((t_feet - t_top) / (s_feet - s_top) - 195 / 160) < 0.01


def _fake_segmenter(monkeypatch, masks):
    import sys, types
    fake = types.ModuleType("imgutils.segment")
    seen = []
    def segment(im):
        seen.append(im.getpixel((0, 0))[0])
        return masks[min(len(seen) - 1, len(masks) - 1)], im
    fake.segment_rgba_with_isnetis = segment
    monkeypatch.setitem(sys.modules, "imgutils", types.ModuleType("imgutils"))
    monkeypatch.setitem(sys.modules, "imgutils.segment", fake)
    return seen


def test_flatten_background_retries_on_a_brighter_copy_when_a_dark_figure_is_missed(monkeypatch):
    import numpy as np
    from PIL import Image
    found = np.zeros((100, 100), dtype=float)
    found[20:80, 20:80] = 1.0
    seen = _fake_segmenter(monkeypatch, [np.zeros((100, 100), dtype=float), found])
    out = io.BytesIO()
    Image.new("RGB", (100, 100), (20, 20, 20)).save(out, "PNG")
    got = Image.open(io.BytesIO(ds.flatten_background(out.getvalue()))).convert("RGB")
    assert seen[1] > seen[0]
    assert got.getpixel((50, 50)) == (20, 20, 20)  # the original pixels survive, not the brightened ones
    assert got.getpixel((5, 50)) == (128, 128, 128)


def test_flatten_background_refuses_to_return_a_blank_sheet(monkeypatch):
    import numpy as np
    from PIL import Image
    _fake_segmenter(monkeypatch, [np.zeros((100, 100), dtype=float)])
    out = io.BytesIO()
    Image.new("RGB", (100, 100), (20, 20, 20)).save(out, "PNG")
    with pytest.raises(ValueError, match="no figure"):
        ds.flatten_background(out.getvalue())
