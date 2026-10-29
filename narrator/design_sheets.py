"""Phase 19b sheet prompts and ComfyUI workflows (19a look) for the design studio.
Pure builders plus two Pillow helpers; no network here."""

import io

from narrator.designs import Design
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE

CHECKPOINT = "NoobAI-XL-Vpred-v1.0.safetensors"
LORA = "Smooth_Booster_v3.safetensors"
UPSCALER = "2x-AnimeSharpV2_RPLKSR_Soft.pth"
BASE_SIZE = (1216, 832)
SHEET_SIZE = (3648, 2496)
SHEET_STYLE = ("anime coloring, cel shading, thick outlines, official art, flat lighting, simple background, "
               "white background")
SHEET_NEGATIVE_EXTRA = "scenery, background clutter, inconsistent outfit, different clothes, different hairstyle"
CHARACTER_SHEETS = ("turnaround", "expressions", "colorguide")
LOCATION_SHEETS = ("establishing", "alternate", "moodkeys", "props")
MOOD_SUFFIXES = ("night, neon lights", "rain, wet street", "dawn, sunrise, soft light")
_SHEET_TAGS = {
    "turnaround": ("character sheet, reference sheet, turnaround, multiple views, front view, from side, "
                   "from behind, full body, standing"),
    "expressions": ("expressions, expression chart, multiple views, portrait, upper body, smile, angry, "
                    "surprised, sad, smirk, closed eyes"),
    "colorguide": ("character sheet, reference sheet, color guide, multiple views, full body, front view, "
                   "from behind, close-up"),
}
_PROPS_TAGS = "still life, no humans, object focus, multiple views, white background"
_SIGNATURE_WORDS = ("mechanical", "cyber", "prosthetic", "robot", "chrome", "implant", "weapon", "sword", "gun")
_PRESENTATION = {"feminine": "1girl", "masculine": "1boy", "androgynous": "1other"}


def subject_for(d: Design) -> str:
    if d.kind == "location":
        return "scenery, no humans"
    if "android" in d.tags:
        return "1other"
    return _PRESENTATION.get(d.presentation, "1other")


def _join(*parts: str) -> str:
    return ", ".join(p for p in parts if p)


def _character_negative(d: Design) -> str:
    return _join(NEGATIVE.replace(", text,", ","), SHEET_NEGATIVE_EXTRA, d.negative)


def _location_negative(d: Design) -> str:
    return _join(NEGATIVE, d.negative)


def _signature_focus(d: Design) -> str:
    for tag in (t.strip() for t in d.tags.split(",")):
        if any(w in tag for w in _SIGNATURE_WORDS):
            return f"{tag} focus"
    return ""


def candidate_prompt(d: Design) -> tuple[str, str]:
    if d.kind == "character":
        return sheet_prompt(d, "turnaround")
    return sheet_prompt(d, "establishing")


def sheet_prompt(d: Design, sheet: str, mood: str | None = None) -> tuple[str, str]:
    if d.kind == "character":
        if sheet not in CHARACTER_SHEETS:
            raise ValueError(f"{sheet!r} is not a character sheet")
        extra = _signature_focus(d) if sheet == "colorguide" else ""
        pos = _join(QUALITY, SHEET_STYLE, _SHEET_TAGS[sheet], extra, subject_for(d), d.tags)
        return pos, _character_negative(d)
    if sheet not in LOCATION_SHEETS:
        raise ValueError(f"{sheet!r} is not a location sheet")
    if sheet == "props":
        return _join(QUALITY, SHEET_STYLE, _PROPS_TAGS, ", ".join(d.props)), _character_negative(d)
    content = d.alt_tags if sheet == "alternate" else d.tags
    style = STYLE
    if sheet == "moodkeys":
        # STYLE's standalone "night" tag would override the mood suffix (dawn, rain...); the mood supplies its own time of day
        style = ", ".join(t for t in STYLE.split(", ") if t != "night")
    pos = _join(QUALITY, style, subject_for(d), content, mood if sheet == "moodkeys" else "")
    return pos, _location_negative(d)


def _base(positive: str, negative: str, seed: int) -> dict:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "20": {"class_type": "LoraLoader", "inputs": {"model": ["4", 0], "clip": ["4", 1], "lora_name": LORA,
               "strength_model": 0.6, "strength_clip": 0.6}},
        "21": {"class_type": "ModelSamplingDiscrete", "inputs": {"model": ["20", 0], "sampling": "v_prediction", "zsnr": True}},
        "22": {"class_type": "RescaleCFG", "inputs": {"model": ["21", 0], "multiplier": 0.6}},
        "10": {"class_type": "CLIPSetLastLayer", "inputs": {"clip": ["20", 1], "stop_at_clip_layer": -2}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["10", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["10", 0]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": BASE_SIZE[0], "height": BASE_SIZE[1], "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 28, "cfg": 4.5, "sampler_name": "euler",
              "scheduler": "normal", "denoise": 1.0, "model": ["22", 0], "positive": ["6", 0],
              "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["4", 2], "tile_size": 512,
              "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
    }


def candidate_workflow(positive: str, negative: str, seed: int) -> dict:
    wf = _base(positive, negative, seed)
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_design", "images": ["8", 0]}}
    return wf


def sheet_workflow(positive: str, negative: str, seed: int, high_res: bool = True) -> dict:
    if not high_res:
        return candidate_workflow(positive, negative, seed)
    wf = _base(positive, negative, seed)
    tiled = {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}
    wf["30"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALER}}
    wf["31"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["30", 0], "image": ["8", 0]}}
    wf["32"] = {"class_type": "ImageScaleBy", "inputs": {"image": ["31", 0], "upscale_method": "lanczos", "scale_by": 0.75}}
    wf["33"] = {"class_type": "VAEEncodeTiled", "inputs": {"pixels": ["32", 0], "vae": ["4", 2], **tiled}}
    wf["34"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 20, "cfg": 4.5, "sampler_name": "euler",
                "scheduler": "normal", "denoise": 0.35, "model": ["22", 0], "positive": ["6", 0],
                "negative": ["7", 0], "latent_image": ["33", 0]}}
    wf["35"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["34", 0], "vae": ["4", 2], **tiled}}
    wf["40"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["30", 0], "image": ["35", 0]}}
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_design", "images": ["40", 0]}}
    return wf


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
    quantized = img.quantize(colors=n + 4)
    flat = quantized.getpalette()
    counts = sorted(quantized.getcolors(), reverse=True)
    colors = [(c, tuple(flat[i * 3:i * 3 + 3])) for c, i in counts]
    if skip_background:  # sheets sit on a white background
        colors = [(c, rgb) for c, rgb in colors if min(rgb) < 235]
    return ["#%02x%02x%02x" % rgb for _c, rgb in colors[:n]]
