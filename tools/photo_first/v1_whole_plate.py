"""Throwaway test: plate -> photoreal person in pose (RealVisXL img2img) -> house anime style (NoobAI img2img + depth CN).
Run from the worktree: ../../../.venv/bin/python <this> [stage1|stage2] [case] [photo_seed]"""
import asyncio, json, sys, urllib.request
from pathlib import Path

sys.path.insert(0, ".")
from narrator.comfyui_backend import ComfyUIBackend
from narrator.designs import load_designs
from tools.imagegen import build

URL = "http://192.168.10.19:8188"
ANIME_DENOISE = 0.70  # locked 2026-11-16: owner picked #3 (seed 6, d70) in every scene; 0.55 kept too much photo
D = Path("../../../design-data")
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
PHOTO_NEG = ("cartoon, anime, illustration, drawing, painting, 3d render, nude, nsfw, cleavage, text, logo, watermark, "
             "extra limbs, extra fingers, deformed, blurry, daylight, sunlight")
CASES = {
    "desk": dict(plate=D / "rins-room/plates/desk-screens.png", who="rin-kageyama", state="offduty",
                 lock="short black pixie undercut with pink tips, black lips, pale grey eyes, silver ear cuff, pale skin, lean frame",
                 photo="RAW photo, a young woman with a short black pixie haircut sitting in a desk chair at a desk with three glowing "
                       "computer monitors, seen from behind over her shoulder, hands on the keyboard, small warm desk lamp, "
                       "dark room at night, blue monitor glow on her, 35mm film, realistic, natural proportions",
                 pose="sitting at a desk, from behind, over the shoulder, hands on keyboard, office chair"),
    "bed": dict(plate=D / "danchi-block/plates/flat-room.png", who="saeko-kirigaya", state="offduty",
                lock="chrome right hand with an amber ring light on the wrist, long straight black hair with blunt bangs, brown eyes",
                photo="RAW photo, a young woman with long straight black hair lying on her side on a futon on a tatami floor, head on "
                      "a pillow, eyes open, one hand resting by her face, under a blanket, small dark apartment at night, low camera "
                      "near the floor, dim light, 35mm film, realistic",
                pose="lying on side, on futon, head on pillow, hand by face, under blanket"),
    "bar": dict(plate=D / "mama-satos-izakaya/plates/along-counter.png", who="saeko-kirigaya", state="work",
                lock="chrome right hand with an amber ring light on the wrist, long straight black hair with blunt bangs, brown eyes",
                photo="RAW photo, a young woman with long straight black hair in a dark jacket sitting on a wooden bar stool at an "
                      "izakaya counter, three-quarter side view, forearms on the counter, holding a small sake cup, warm paper lantern "
                      "light, night, 35mm film, realistic, natural proportions",
                pose="sitting on bar stool, at counter, forearms on counter, holding cup, from side"),
}


def comfy_free():
    req = urllib.request.Request(f"{URL}/free", data=b'{"unload_models":true,"free_memory":true}',
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30)


def photo_wf(plate_name, text, seed, denoise=0.75):
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "RealVisXL_V5.0_fp16.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": PHOTO_NEG, "clip": ["4", 1]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": plate_name}},
        "12": {"class_type": "ImageScale", "inputs": {"image": ["11", 0], "upscale_method": "lanczos", "width": 1216, "height": 832, "crop": "center"}},
        "13": {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 30, "cfg": 5.0, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                                                   "denoise": denoise, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["13", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_phototest/photo", "images": ["8", 0]}},
    }


def anime_wf(c, photo_name, depth_name, seed, denoise):
    d = load_designs()[c["who"]]
    w = d.wardrobe[c["state"]]
    from tools.image_studio import _subject
    subj = _subject(d)
    text = ", ".join([c["pose"], subj, "solo", d.appearance, c["lock"], w.tags, "anime screenshot coloring, cel shading, thick outlines, night, cyberpunk, high contrast"])
    wf = build(text, "subject", False, "photorealistic, photo, 3d, realistic, text, logo, extra limbs, cleavage", "base", seed, subject=subj)
    wf["5"]["inputs"].update(width=1216, height=832)
    wf["30"] = {"class_type": "LoadImage", "inputs": {"image": photo_name}}
    wf["31"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["30", 0], "vae": ["4", 2]}}
    wf["40"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "noob_sdxl_controlnet_depth.safetensors"}}
    wf["41"] = {"class_type": "LoadImage", "inputs": {"image": depth_name}}
    wf["42"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "control_net": ["40", 0],
                                                                  "image": ["41", 0], "strength": 0.7, "start_percent": 0.0, "end_percent": 0.7}}
    wf["3"]["inputs"].update(latent_image=["31", 0], denoise=denoise, positive=["42", 0], negative=["42", 1])
    wf["9"]["inputs"]["filename_prefix"] = "nightwire_phototest/anime"
    return wf


async def stage1(case, seeds):
    c = CASES[case]
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=600.0)
    name = await be.upload_image(f"pt-plate-{case}.png", c["plate"].read_bytes())
    for s in seeds:
        (OUT / f"{case}-photo-{s}.png").write_bytes(await be.run_workflow(photo_wf(name, c["photo"], s)))
        print(case, "photo", s, flush=True)


async def stage2(case, photo_seed, seeds, denoise):
    from tools.shorts.plate_camera import depth_map
    c = CASES[case]
    photo = OUT / f"{case}-photo-{photo_seed}.png"
    depth = OUT / f"{case}-photo-{photo_seed}.depth.png"
    if not depth.exists():
        depth_map(photo).save(depth)
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=600.0)
    pn = await be.upload_image(f"pt-photo-{case}-{photo_seed}.png", photo.read_bytes())
    dn = await be.upload_image(f"pt-depth-{case}-{photo_seed}.png", depth.read_bytes())
    for s in seeds:
        (OUT / f"{case}-anime-{photo_seed}-{s}-d{int(denoise*100)}.png").write_bytes(await be.run_workflow(anime_wf(c, pn, dn, s, denoise)))
        print(case, "anime", photo_seed, s, denoise, flush=True)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "stage1":
            for case in (sys.argv[2:] or CASES):
                asyncio.run(stage1(case, [11, 22, 33]))
        else:
            case, ps = sys.argv[2], int(sys.argv[3])
            for dn in (ANIME_DENOISE,):
                asyncio.run(stage2(case, ps, [5, 6], dn))
    finally:
        comfy_free()
