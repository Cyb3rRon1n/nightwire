import io

from PIL import Image

from tools.fix_area import bounds, changed_outside, crop_around, fix_workflow, rough_fill, soft_mask, stitch


SQUARE = [(150, 150), (250, 150), (250, 250), (150, 250)]


def _png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_crop_is_square_with_context_and_stays_inside_the_image():
    assert crop_around((1000, 800), (100, 100, 200, 200)) == (22, 22, 278, 278)
    x0, y0, x1, y1 = crop_around((1000, 800), (950, 700, 990, 790))
    assert x1 - x0 == y1 - y0 and x1 <= 1000 and y1 <= 800 and x0 <= 950 and y0 <= 700


def test_mask_feathers_and_stops_short_of_the_far_edge():
    mask = soft_mask((400, 400), SQUARE, feather=10)
    assert mask.getpixel((200, 200)) == 255
    assert 0 < mask.getpixel((150, 200)) < 255
    assert mask.getpixel((5, 5)) == 0


def test_stitch_changes_nothing_outside_the_mask():
    base = Image.new("RGB", (400, 300), (10, 20, 30))
    shape = [(100, 100), (180, 100), (180, 180), (100, 180)]
    crop = crop_around((400, 300), bounds(shape))
    repaint = Image.new("RGB", (1024, 1024), (200, 0, 0))
    after, mask = stitch(_png(base), _png(repaint), crop, shape, feather=6)
    assert changed_outside(_png(base), after, mask) == 0
    assert Image.open(io.BytesIO(after)).getpixel((140, 140)) == (200, 0, 0)


def test_changed_outside_counts_stray_pixels():
    base = Image.new("RGB", (50, 50), (0, 0, 0))
    moved = base.copy()
    moved.putpixel((1, 1), (1, 0, 0))  # small enough to vanish in a greyscale conversion
    assert changed_outside(_png(base), _png(moved), Image.new("L", (50, 50), 0)) == 1


def test_workflow_samples_only_the_masked_crop_with_differential_diffusion():
    wf = fix_workflow("pos", "neg", 7, "crop.png", "mask.png", 0.4)
    assert "5" not in wf
    types = {n["class_type"] for n in wf.values()}
    assert {"DifferentialDiffusion", "SetLatentNoiseMask", "LoadImageMask"} <= types
    sampler = wf["3"]["inputs"]
    assert sampler["denoise"] == 0.4
    assert wf[sampler["model"][0]]["class_type"] == "DifferentialDiffusion"
    assert wf[sampler["latent_image"][0]]["class_type"] == "SetLatentNoiseMask"


def test_rough_fill_paints_only_inside_the_mask():
    base = Image.new("RGB", (400, 400), (0, 0, 0))
    filled = rough_fill(base, soft_mask((400, 400), SQUARE, feather=2), (230, 50, 110))
    assert filled.getpixel((200, 200)) == (230, 50, 110)
    assert filled.getpixel((5, 5)) == (0, 0, 0)
