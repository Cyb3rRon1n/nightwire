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
