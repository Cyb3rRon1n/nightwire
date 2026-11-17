"""Throwaway test v3: the photo is painted only inside a person mask on the plate (room kept exactly), dressed in the
character's real outfit and colours, and checked for person count before use.
Run from the worktree: ../../../.venv/bin/python <this> [case...]"""
import asyncio, io, sys
from pathlib import Path

sys.path.insert(0, ".")
from PIL import Image, ImageDraw, ImageFilter
from narrator.comfyui_backend import ComfyUIBackend

sys.path.insert(0, str(Path(__file__).parent))
from v1_whole_plate import comfy_free, URL
from v2_house_look import CASES as BASE

OUT = Path(__file__).parent / "out"
W, H = 1216, 832
NEG = ("cartoon, anime, illustration, drawing, painting, 3d render, cgi, nude, nsfw, cleavage, text, logo, watermark, "
       "two people, multiple people, crowd, extra person, reflection of a person, floating, levitating, sitting on nothing, "
       "extra legs, extra arms, missing limbs, fused fingers, extra fingers, deformed hands, distorted furniture, blurry, daylight")
RIN = "oversized dark grey knit sweater with the sleeves over her hands, loose black cargo joggers, white sneakers"
SAEKO_OFF = "oversized grey sweater, black leggings"
SAEKO_WORK = "cropped navy blue jacket with thin red trim over a black high-collar top zipped up, dark opaque tights, black ankle boots, black gloves"
# mask (x0, y0, x1, y1) as frame fractions: where the person may appear; everything else stays the plate
CASES = {
    "desk": ((0.52, 0.12, 1.0, 1.0), "RAW photo, a young woman with a short black pixie haircut, wearing an " + RIN + ", sitting on a "
             "desk chair at the desk, seen from behind over her right shoulder, both hands on the keyboard, lit by the blue monitor glow"),
    "bed": ((0.24, 0.42, 0.98, 0.98), "RAW photo, a young woman with long straight black hair and blunt bangs, wearing an " + SAEKO_OFF +
            ", lying on her side on the futon facing the camera, head on the pillow, eyes open, one hand resting by her face, a blanket over her legs"),
    "bar": ((0.5, 0.05, 1.0, 1.0), "RAW photo, a young woman with long straight black hair and blunt bangs, wearing a " + SAEKO_WORK +
            ", seated low on a round bar stool at the wooden counter, her whole head and shoulders in frame, three-quarter view from behind, forearms resting on the counter, a small sake cup"),
    "window": ((0.18, 0.3, 0.66, 0.96), "RAW photo, a young woman with a short black pixie haircut, wearing an " + RIN + ", sitting on the "
               "bed hugging her knees, seen from behind, looking out of the window at the city lights, pink neon light on her"),
    "rail": ((0.52, 0.18, 0.96, 1.0), "RAW photo, a young woman with long straight black hair and blunt bangs, wearing a " + SAEKO_WORK +
             ", standing with her forearms resting on the metal railing, side view, looking out at the city lights, wind in her hair"),
    "train": ((0.0, 0.38, 0.46, 1.0), "RAW photo, a young woman with a short black pixie haircut, wearing an " + RIN + ", sitting on the "
              "train seat on the left, side view, head leaning back against the window, hands in her lap, feet on the floor"),
}
STYLE = ", night, 35mm film, realistic, natural proportions, she is the only person"


def mask_png(box) -> bytes:
    m = Image.new("L", (W, H), 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(m).rectangle((x0 * W, y0 * H, x1 * W, y1 * H), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(48))
    b = io.BytesIO(); Image.merge("RGB", (m, m, m)).save(b, "PNG")
    return b.getvalue()


def wf(plate, mask, text, seed):
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "RealVisXL_V5.0_fp16.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["4", 1]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": plate}},
        "12": {"class_type": "ImageScale", "inputs": {"image": ["11", 0], "upscale_method": "lanczos", "width": W, "height": H, "crop": "center"}},
        "13": {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}},
        "14": {"class_type": "LoadImage", "inputs": {"image": mask}},
        "15": {"class_type": "ImageToMask", "inputs": {"image": ["14", 0], "channel": "red"}},
        "16": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["13", 0], "mask": ["15", 0]}},
        "18": {"class_type": "DifferentialDiffusion", "inputs": {"model": ["4", 0]}},  # soft mask edges blend into the plate
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 34, "cfg": 5.0, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                                                   "denoise": 0.97, "model": ["18", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["16", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "17": {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["12", 0], "source": ["8", 0], "x": 0, "y": 0,
                                                                "resize_source": False, "mask": ["15", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_phototest/masked", "images": ["17", 0]}},
    }


def people(png: Path) -> int:
    from imgutils.detect import detect_person
    return sum(1 for _, _, score in detect_person(Image.open(png).convert("RGB")) if score > 0.5)


async def run(case, seeds):
    box, text = CASES[case]
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=600.0)
    plate = await be.upload_image(f"pt-plate-{case}.png", BASE[case]["plate"].read_bytes())
    mask = await be.upload_image(f"pt3-mask-{case}.png", mask_png(box))
    for s in seeds:
        out = OUT / f"{case}-masked-{s}.png"
        out.write_bytes(await be.run_workflow(wf(plate, mask, text + STYLE, s)))
        n = people(out)
        print(case, s, f"people={n}", "REJECT" if n >= 2 else "OK", flush=True)  # the detector misses lying/cropped people


if __name__ == "__main__":
    try:
        for case in (sys.argv[1:] or CASES):
            asyncio.run(run(case, [11, 22, 33, 44]))
    finally:
        comfy_free()
