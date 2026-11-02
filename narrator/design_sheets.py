"""Phase 19b sheet prompts and ComfyUI workflows (19a look) for the design studio.
Pure builders plus two Pillow helpers; no network here."""

import io

from narrator.designs import Design
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE, _below_chest

CHECKPOINT = "NoobAI-XL-Vpred-v1.0.safetensors"
LORA = "Smooth_Booster_v3.safetensors"
UPSCALER = "2x-AnimeSharpV2_RPLKSR_Soft.pth"
BASE_SIZE = (1216, 832)
SHEET_SIZE = (3648, 2496)
SHEET_STYLE = ("anime coloring, cel shading, thick outlines, official art, flat lighting, simple background, "
               "white background")
# Turnarounds and colour guides: the portraits' drawn look under plain light on mid-grey, so a sheet shows the same
# person in true colours (owner approved, 2026-11-02; glossy `official art` read as a different person).
CHARACTER_SHEET_STYLE = ("anime screenshot, anime coloring, cel shading, thick outlines, simple background, (grey background:1.3), "
                         "even lighting, front lighting, cyberpunk")
_SHEET_GUARD = ("(realistic:1.4), (photorealistic:1.4), (photo (medium):1.3), (3d:1.3), (semi-realistic:1.3), painterly, oil painting, "
                "(skin texture:1.3), pores, airbrushed, detailed skin, hairy, (shadow over face:1.2), (dark face:1.2), low key, "
                "underexposed, silhouette, black background, multiple heads, extra heads, disembodied head, "
                "(white background:1.4), (light background:1.2)")  # "white" pulls pale outfits that change from view to view
# Tattoos, scars and the like belong in each character's own tags: listed here they appeared on everyone.
CHARACTER_MATURE = "mature, adult, serious, cyberpunk, techwear"
CHARACTER_QUALITY = QUALITY.replace("safe", "sensitive")  # suggestive allowed, explicit not
CHARACTER_NEGATIVE_EXTRA = ("nude, nipples, pussy, penis, sex, explicit, loli, shota, child, petite, flat chest, young, "
                            "teenage, aged down, chibi, kawaii, moe, cute, big eyes, deformed")
SHEET_NEGATIVE_EXTRA = ("scenery, background clutter, inconsistent outfit, different clothes, different hairstyle, "
                        "floating object, mismatched footwear, extra arms, extra legs")
CHARACTER_SHEETS = ("turnaround", "expressions", "colorguide", "portrait")
LOCATION_SHEETS = ("establishing", "alternate", "moodkeys", "props")
MOOD_SUFFIXES = ("night, neon lights", "rain, wet street", "dawn, sunrise, soft light")
_SHEET_TAGS = {
    "turnaround": ("character sheet, reference sheet, turnaround, multiple views, front view, from side, "
                   "from behind, full body, standing"),
}
# One image per expression, assembled into a grid: a single render drawing 6-8 heads picks its own layout, drifts
# between panels and strands carried items in mid-air (owner audit, 2026-11-01).
EXPRESSIONS = (("Neutral", "expressionless, closed mouth"), ("Smile", "smile, closed mouth"),
               ("Angry", "angry, frown, clenched teeth"), ("Surprised", "surprised, wide-eyed, open mouth"),
               ("Sad", "sad, looking down, closed mouth"), ("Smirk", "smirk"))
# AI characters default to logic over feeling and are still learning emotion (owner, 2026-11-01), so their sheets
# show restraint and misfires instead of full human moods.
AI_EXPRESSIONS = (("Neutral", "expressionless, closed mouth"), ("Polite", "light smile, closed mouth, expressionless"),
                  ("Attentive", "expressionless, head tilt, closed mouth"), ("Confused", "confused, expressionless, closed mouth"),
                  ("Processing", "expressionless, looking to the side, closed mouth"), ("Almost sad", "expressionless, looking down, closed mouth"))
EXPRESSION_SIZE = (1024, 1024)
_BELOW_FRAME_WORDS = ("heels", "fishnet", "garter", "hakama", "slit", "belt", "holster", "knee", "hip",
                      "breasts", "waist", "tall", "slender", "toned", "lean", "wiry", "muscular", "abs", "shoulders",
                      "gaunt", "cleavage", "neckline", "midriff", "backless", "gloves", "rings", "bracelet", "sleeve")
_EXPRESSION_WORDS = ("smile", "smirk", "grin", "scowl", "expression", "stern", "serene", "calm")
_EXPRESSION_NEGATIVE = ("multiple views, character sheet, expression chart, turnaround, split screen, full body, "
                        "child face, baby face, round face, youthful face, cowboy shot, breast focus, cleavage, hand up, hands, hand on own face, hand on own chin, fingers, "
                        "holding, cigarette, smoking, floating object, extra hands, sharp teeth, vampire, monster, "
                        "pink skin, red skin, blue skin, purple skin, colored skin, monochrome, red theme, pink theme, neon lights, backlighting")
# Neon light tints faces and pulls older men towards realism; these keep portraits in the same drawn style.
_PORTRAIT_GUARD = ("realistic, photorealistic, photo (medium), 3d, semi-realistic, painterly, oil painting, skin texture, pores, "
                   "airbrushed, (blue skin:1.3), (colored skin:1.3), (grey skin:1.3), (shadow over face:1.2)")
_PROPS_TAGS = "still life, no humans, object focus, multiple views, white background"
_PRESENTATION = {"feminine": "1girl", "masculine": "1boy", "androgynous": "1other"}


def subject_for(d: Design) -> str:
    if d.kind == "location":
        return "scenery, no humans"
    if "android" in d.tags:
        return "1other"
    return _PRESENTATION.get(d.presentation, "1other")


def _join(*parts: str) -> str:
    return ", ".join(p for p in parts if p)


def _character_negative(d: Design, mature: bool = True) -> str:
    return _join(NEGATIVE.replace(", text,", ","), SHEET_NEGATIVE_EXTRA, CHARACTER_NEGATIVE_EXTRA if mature else "", d.negative)


def _styled_negative(d: Design, guard: str, scene: bool = False) -> str:
    """The character negative without the tags this sheet's own look asks for, plus the guard that holds that look."""
    neg = _character_negative(d)
    for allowed in ("flat color, ", "simple background, ", *(("scenery, background clutter, ",) if scene else ())):
        neg = neg.replace(allowed, "")
    return _join(neg, guard)


def _location_negative(d: Design) -> str:
    return _join(NEGATIVE, d.negative)


def candidate_prompt(d: Design) -> tuple[str, str]:
    if d.kind == "character":
        return sheet_prompt(d, "turnaround")
    return sheet_prompt(d, "establishing")


def sheet_prompt(d: Design, sheet: str, mood: str | None = None) -> tuple[str, str]:
    if d.kind == "character":
        if sheet not in CHARACTER_SHEETS:
            raise ValueError(f"{sheet!r} is not a character sheet")
        if sheet == "colorguide":
            raise ValueError("the colour guide is built from the turnaround, see colour_guide")
        if sheet == "portrait":
            return portrait_prompt(d)
        pos = _join(CHARACTER_QUALITY, CHARACTER_SHEET_STYLE, CHARACTER_MATURE, _SHEET_TAGS[sheet], subject_for(d), ", ".join(d.required),
                    ", ".join(t for t in (x.strip() for x in d.tags.split(",")) if t not in d.required))
        return pos, _styled_negative(d, _SHEET_GUARD)
    if sheet not in LOCATION_SHEETS:
        raise ValueError(f"{sheet!r} is not a location sheet")
    if sheet == "props":
        return _join(QUALITY, SHEET_STYLE, _PROPS_TAGS, ", ".join(d.props)), _character_negative(d, mature=False)
    content = d.alt_tags if sheet == "alternate" else d.tags
    style = STYLE
    if sheet == "moodkeys":
        # STYLE's standalone "night" tag would override the mood suffix (dawn, rain...); the mood supplies its own time of day
        style = ", ".join(t for t in STYLE.split(", ") if t != "night")
    pos = _join(QUALITY, style, subject_for(d), content, mood if sheet == "moodkeys" else "")
    return pos, _location_negative(d)


def expressions_for(d: Design) -> tuple[tuple[str, str], ...]:
    return AI_EXPRESSIONS if "android" in d.tags else EXPRESSIONS


def _face_tags(d: Design) -> list[str]:
    """The character's face and upper-body canon: no carried items, lower body or fixed mood."""
    held = {h.strip() for h in d.held}
    return [t for t in dict.fromkeys(x.strip() for x in d.tags.split(",")) if t not in held and t not in d.required
            and not _below_chest(t) and not any(w in t for w in (*_BELOW_FRAME_WORDS, *_EXPRESSION_WORDS))]


def portrait_prompt(d: Design) -> tuple[str, str]:
    """The avatar is the neutral expression panel at full quality, so avatar and expressions share one face and look."""
    return expression_prompts(d)[0][1:]


def expression_prompts(d: Design) -> list[tuple[str, str, str]]:
    """(label, positive, negative) per panel, in the scene look like the portrait (owner pick, 2026-11-01): the
    character's face and upper-body canon only. Tags for carried items,
    the lower body and a fixed mood are left out, so each panel can only show the face and the mood it's asking for."""
    held = {h.strip() for h in d.held}
    tags = [t.strip() for t in d.tags.split(",")]
    face = _face_tags(d)
    fang = any(w in tags for w in ("fang", "fangs"))
    negative = _join(_styled_negative(d, _PORTRAIT_GUARD, scene=True), _EXPRESSION_NEGATIVE, "" if fang else "fang, fangs", ", ".join(held))
    return [(label, _join(CHARACTER_QUALITY, STYLE, "mature, adult, solo, portrait, close-up, face focus, looking at viewer",
                          subject_for(d), mood, ", ".join(d.required), ", ".join(face)), negative) for label, mood in expressions_for(d)]


def _base(positive: str, negative: str, seed: int, *, checkpoint: str = CHECKPOINT, lora: str | None = LORA,
          lora_strength: float = 0.6, steps: int = 28, cfg: float = 4.5, sampler: str = "euler",
          scheduler: str = "normal", vpred: bool = True, clip_skip: int = -2) -> dict:
    wf = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}}}
    model, clip = ["4", 0], ["4", 1]
    if lora and lora != "none":
        wf["20"] = {"class_type": "LoraLoader", "inputs": {"model": model, "clip": clip, "lora_name": lora,
                    "strength_model": lora_strength, "strength_clip": lora_strength}}
        model, clip = ["20", 0], ["20", 1]
    if vpred:
        wf["21"] = {"class_type": "ModelSamplingDiscrete", "inputs": {"model": model, "sampling": "v_prediction", "zsnr": True}}
        wf["22"] = {"class_type": "RescaleCFG", "inputs": {"model": ["21", 0], "multiplier": 0.6}}
        model = ["22", 0]
    wf["10"] = {"class_type": "CLIPSetLastLayer", "inputs": {"clip": clip, "stop_at_clip_layer": clip_skip}}
    wf["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["10", 0]}}
    wf["7"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["10", 0]}}
    wf["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": BASE_SIZE[0], "height": BASE_SIZE[1], "batch_size": 1}}
    wf["3"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler,
          "scheduler": scheduler, "denoise": 1.0, "model": model, "positive": ["6", 0],
          "negative": ["7", 0], "latent_image": ["5", 0]}}
    wf["8"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["4", 2], "tile_size": 512,
          "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
    return wf


def candidate_workflow(positive: str, negative: str, seed: int, **options) -> dict:
    wf = _base(positive, negative, seed, **options)
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_design", "images": ["8", 0]}}
    return wf


def sheet_workflow(positive: str, negative: str, seed: int, high_res: bool = True, size: tuple[int, int] | None = None,
                   **options) -> dict:
    if not high_res:
        return candidate_workflow(positive, negative, seed, **options)
    wf = _base(positive, negative, seed, **options)
    if size:
        wf["5"]["inputs"].update(width=size[0], height=size[1])
    tiled = {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}
    wf["30"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALER}}
    wf["31"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["30", 0], "image": ["8", 0]}}
    wf["32"] = {"class_type": "ImageScaleBy", "inputs": {"image": ["31", 0], "upscale_method": "lanczos", "scale_by": 0.75}}
    wf["33"] = {"class_type": "VAEEncodeTiled", "inputs": {"pixels": ["32", 0], "vae": ["4", 2], **tiled}}
    wf["34"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 20,
                "cfg": options.get("cfg", 4.5), "sampler_name": options.get("sampler", "euler"),
                "scheduler": options.get("scheduler", "normal"), "denoise": 0.35,
                "model": wf["3"]["inputs"]["model"], "positive": ["6", 0],
                "negative": ["7", 0], "latent_image": ["33", 0]}}
    wf["35"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["34", 0], "vae": ["4", 2], **tiled}}
    wf["40"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["30", 0], "image": ["35", 0]}}
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_design", "images": ["40", 0]}}
    return wf


def expression_grid(panels: list[tuple[str, bytes]], columns: int = 3) -> bytes:
    from PIL import Image, ImageDraw
    frames = [(label, Image.open(io.BytesIO(b)).convert("RGB")) for label, b in panels]
    w, h = frames[0][1].size
    rows = -(-len(frames) // columns)
    sheet = Image.new("RGB", (w * columns, h * rows), "#17151c")
    draw = ImageDraw.Draw(sheet)
    for i, (label, frame) in enumerate(frames):
        x, y = (i % columns) * w, (i // columns) * h
        sheet.paste(frame, (x, y))
        draw.text((x + 16, y + 12), label, fill="#ffffff", stroke_width=3, stroke_fill="#000000", font_size=max(18, h // 24))
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


def flatten_background(png: bytes, grey: int = 128) -> bytes:
    """Puts the figures on one flat grey, so a whole cast's body sheets match; prompts alone land anywhere from near-white
    to near-black. A segmentation model, because colour fills ate dark dresses that matched a dark backdrop (pilot,
    2026-11-02). Generated swatches go with the backdrop: the record's palette comes from extract_palette."""
    import numpy as np
    from imgutils.segment import segment_rgba_with_isnetis
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    alpha = np.clip((segment_rgba_with_isnetis(im)[0] - 0.25) / 0.5, 0, 1)  # the model is unsure on dark cloth: firm up its soft edges
    im.paste((grey, grey, grey), mask=Image.fromarray(((1 - alpha) * 255).astype("uint8")))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def colour_guide(turnaround: bytes, palette: list[str], head: tuple[int, int, int, int] | None = None, grey: int = 128) -> bytes:
    """The turnaround plus a close-up cropped from it and its palette. Built, not rendered: two separate renders of one
    character never fully agreed on hair and outfit (pilot, 2026-11-02), and the reference has to have one answer."""
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(turnaround)).convert("RGB")
    side = im.height // 2
    out = Image.new("RGB", (im.width + side, im.height), (grey, grey, grey))
    out.paste(im, (0, 0))
    if head:
        x0, y0, x1, y1 = head
        pad = (x1 - x0) // 3
        out.paste(im.crop((max(x0 - pad, 0), max(y0 - pad, 0), x1 + pad, y1 + pad)).resize((side, side), Image.LANCZOS), (im.width, 0))
    draw = ImageDraw.Draw(out)
    for i, colour in enumerate(palette):
        top = side + i * side // max(len(palette), 1)
        draw.rectangle((im.width, top, out.width, top + side // max(len(palette), 1)), fill=colour)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def join_strip(images: list[bytes]) -> bytes:
    from PIL import Image
    frames = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
    strip = Image.new("RGB", (sum(f.width for f in frames), max(f.height for f in frames)))
    x = 0
    for f in frames:
        strip.paste(f, (x, 0))
        x += f.width
    out = io.BytesIO()
    strip.save(out, "PNG")
    return out.getvalue()


def extract_palette(png: bytes, n: int = 6, skip_background: bool = True) -> list[str]:
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img.thumbnail((256, 256))
    quantized = img.quantize(colors=n + 18)
    flat = quantized.getpalette()
    counts = sorted(quantized.getcolors(), reverse=True)
    colors = [(c, tuple(flat[i * 3:i * 3 + 3])) for c, i in counts]
    if skip_background:  # body sheets sit on flat mid-grey
        colors = [(c, rgb) for c, rgb in colors if max(abs(v - 128) for v in rgb) > 12]
    kept = []
    for _c, rgb in colors:  # a dark outfit otherwise fills the palette with near-identical blacks
        if all(sum(abs(a - b) for a, b in zip(rgb, other)) > 36 for other in kept):
            kept.append(rgb)
    # Most of the area first, then the strongest accents: small details like coloured hair tips rarely win on area.
    main, rest = kept[:max(n - 2, 1)], kept[max(n - 2, 1):]
    rest.sort(key=lambda rgb: max(rgb) - min(rgb), reverse=True)
    return ["#%02x%02x%02x" % rgb for rgb in (main + rest)[:n]]
