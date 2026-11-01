from tools.imagegen import SIZES, build


def test_wallpaper_sizes_end_at_exact_resolution():
    for name, (w, h, bw, bh, high_res) in SIZES.items():
        wf = build("rooftop bar", "scene", False, "", name, 7)
        assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == (bw, bh)
        final = wf[wf["9"]["inputs"]["images"][0]]
        if high_res:
            assert final["class_type"] == "ImageScale" and (final["inputs"]["width"], final["inputs"]["height"]) == (w, h)


def test_kinds():
    scene = build("alley", "scene", False, "", "base", 1)
    assert "scenery, no humans" in scene["6"]["inputs"]["text"] and "safe" in scene["6"]["inputs"]["text"]
    char = build("1girl", "character", False, "", "base", 1)
    assert "sensitive" in char["6"]["inputs"]["text"] and "nude" in char["7"]["inputs"]["text"]
    raw = build("just this", "scene", True, "", "base", 1)
    assert raw["6"]["inputs"]["text"] == "just this"


def test_portrait_kind_is_a_bust_in_world():
    wf = build("1girl, black hair", "portrait", False, "", "portrait", 1)
    assert "upper body, portrait" in wf["6"]["inputs"]["text"] and "full body" in wf["7"]["inputs"]["text"]
    assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == (832, 1216)


def test_day_subject_and_crowd_kinds():
    day = build("alley", "scene", False, "", "base", 1, day=True)
    assert "daylight" in day["6"]["inputs"]["text"] and "night" not in day["6"]["inputs"]["text"]
    assert "night" in build("alley", "scene", False, "", "base", 1)["6"]["inputs"]["text"]
    assert "no humans" not in build("1girl, standing", "subject", False, "", "base", 1)["6"]["inputs"]["text"]
    assert "crowd, many people" in build("pachinko hall", "crowd", False, "", "base", 1)["6"]["inputs"]["text"]


def test_checkpoint_lora_and_sampler_overrides():
    wf = build("x", "plain", True, "n", "base", 1, checkpoint="NoobAI-XL-v1.0.safetensors",
               lora="wlop.safetensors", lora_strength=0.7, vpred=False, sampler="dpmpp_2m",
               scheduler="karras", cfg=6.0, steps=30)
    assert wf["4"]["inputs"]["ckpt_name"] == "NoobAI-XL-v1.0.safetensors"
    assert wf["20"]["inputs"]["lora_name"] == "wlop.safetensors" and wf["20"]["inputs"]["strength_model"] == 0.7
    assert "21" not in wf and "22" not in wf and wf["3"]["inputs"]["model"] == ["20", 0]
    k = wf["3"]["inputs"]
    assert (k["sampler_name"], k["scheduler"], k["cfg"], k["steps"]) == ("dpmpp_2m", "karras", 6.0, 30)


def test_no_lora_and_high_res_refine_follow_options():
    wf = build("x", "plain", False, "", "1080p", 1, lora="none", cfg=6.0, sampler="dpmpp_2m", scheduler="karras")
    assert "20" not in wf and wf["3"]["inputs"]["model"] == ["22", 0]
    refine = wf["34"]["inputs"]
    assert (refine["sampler_name"], refine["scheduler"], refine["cfg"]) == ("dpmpp_2m", "karras", 6.0)
    assert refine["model"] == ["22", 0] and refine["steps"] == 20 and refine["denoise"] == 0.35


def test_character_kind_matches_the_design_studio_sheet_composition():
    wf = build("android, blank eyes", "character", False, "", "base", 1, subject="1other")
    pos, neg = wf["6"]["inputs"]["text"], wf["7"]["inputs"]["text"]
    assert "character sheet, reference sheet, turnaround" in pos and "full body, standing" in pos
    assert "1other" in pos and "grey background" in pos and "official art" in pos
    assert "big eyes" in neg and "different hairstyle" in neg and "scenery" in neg


def test_mature_tags_are_adult_and_removable():
    on = build("black hair", "portrait", False, "", "portrait", 1)
    assert "25 years old" in on["6"]["inputs"]["text"] and "big eyes" in on["7"]["inputs"]["text"]
    assert "child face" in on["7"]["inputs"]["text"] and "1girl" in on["6"]["inputs"]["text"]
    off = build("black hair", "portrait", False, "", "portrait", 1, mature=False)
    assert "25 years old" not in off["6"]["inputs"]["text"] and "child face" not in off["7"]["inputs"]["text"]


def test_sheet_style_portrait_swaps_the_scene_look():
    wf = build("black hair", "portrait", False, "", "portrait", 1, sheet_style=True)
    pos = wf["6"]["inputs"]["text"]
    assert "official art" in pos and "grey background" in pos and "anime screenshot" not in pos
    assert "scenery, background clutter" in wf["7"]["inputs"]["text"]


def test_design_defaults_reproduce_an_approved_design():
    from tools.imagegen import design_defaults
    dd = design_defaults("hachi")
    assert dd["subject"] == "1other" and dd["seed"] == 1266373671 and dd["kind"] == "character"
    assert "android" in dd["prompt"] and "wide hips" in dd["negative"]


def test_mature_tags_follow_the_subject():
    boy = build("black hair", "portrait", False, "", "portrait", 1, subject="1boy")["6"]["inputs"]["text"]
    assert "mature male" in boy and "mature female" not in boy
    other = build("android", "subject", False, "", "base", 1, subject="1other")["6"]["inputs"]["text"]
    assert "mature female" not in other and "adult" in other


def test_closeup_reproduces_the_owners_favourite_look():
    wf = build("casual outfit, sfw", "closeup", False, "", "base", 3654015602)
    pos, neg = wf["6"]["inputs"]["text"], wf["7"]["inputs"]["text"]
    assert pos.startswith("masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, sensitive, 1girl, solo")
    assert "yellow accents" in pos and "fully clothed" in pos and "nsfw" not in pos
    assert "nude" in neg and "child" in neg
    assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == (1216, 832)
