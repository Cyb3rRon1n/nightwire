"""Test v5: photo-first with the pose set first. A grey library figure is placed on the plate (sized by the plate's camera,
with whatever stands in front of it cut away), and its pose skeleton + depth guide the photo step through ControlNet Union
ProMax (xinsir, Apache-2.0). The anime step is the locked v1 recipe (NoobAI img2img 0.70 + depth from the photo).
Fixes the owner's 2026-11-28 note: Rin's desk shot had the wanted style but she sat inside the table.
Run from the repo root: .venv/bin/python tools/photo_first/v5_guided.py guides | photo SHOT | anime SHOT PHOTO_SEED"""
import asyncio, json, sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).parent))
from tools.greybox_library import insert
from tools.shorts import plate_camera
from narrator.designs import load_designs

D = Path("design-data")
LIB = D / "greybox-library"
OUT = Path(__file__).parent / "out" / "v5"
URL = "http://192.168.10.41:8188"
# shot: plate, character, wardrobe state, library cell (pose/camera), feet (x, y of frame; y > 1 = below the frame),
#       photo prompt, anime pose tags, lock tags
SHOTS = {
    "rin-desk": dict(plate=D / "rins-room/plates/desk-screens.png", who="rin-kageyama", state="offduty",
                     cell="sit-stool/ws-back-above", feet=(0.62, 1.55), front=False,
                     lock="short black pixie undercut with pink tips, black lips, pale grey eyes, silver ear cuff, pale skin, lean frame",
                     photo="RAW photo, a young woman with a short black pixie haircut sitting in an office chair in front of a desk, seen "
                           "from behind over her shoulder, her forearms resting on the desk edge, hands on the keyboard, two glowing "
                           "computer monitors, dark room at night, cold blue monitor glow on her hair and shoulders, 35mm film, realistic",
                     pose="sitting on office chair, in front of desk, from behind, over the shoulder, hands on keyboard, monitor glow"),
    "saeko-bar": dict(plate=D / "mama-satos-izakaya/plates/toward-far-end.png", who="saeko-kirigaya", state="work",
                      cell="sit-stool/ws-back-eye", feet=(0.62, 0.95),
                      lock="chrome right hand with an amber ring light on the wrist, long straight black hair with blunt bangs, brown eyes",
                      photo="RAW photo, a young woman with long straight black hair in a dark jacket sitting on a bar stool at a wooden "
                            "izakaya counter, seen from behind, her back to the camera, both forearms resting on the counter top, warm "
                            "paper lantern light catching the edge of her hair, bottles glowing on the shelves, night, 35mm film, realistic",
                      pose="sitting on bar stool, at counter, from behind, forearm on counter, lantern rim light"),
    "saeko-home": dict(plate=D / "danchi-block/plates/flat-room.png", who="saeko-kirigaya", state="offduty",
                       cell="cross-legged-deck/ws-front-eye", feet=(0.56, 0.80),
                       lock="chrome right hand with an amber ring light on the wrist, long straight black hair with blunt bangs, brown eyes",
                       photo="RAW photo, a young woman with long straight black hair sitting cross-legged on a futon on a tatami floor in a "
                             "dark small apartment at night, facing the camera, head bowed, her hair falling forward, a small amber light glowing "
                             "on her right wrist lighting her face from below, cold blue light from the sliding door behind her, "
                             "35mm film, realistic",
                       pose="sitting cross-legged on futon, head down, hair over face, hands in lap, amber wrist light, dark room"),
}


def guides(name):
    s = SHOTS[name]
    entry = LIB / s["cell"]
    meta = json.loads((entry / "meta.json").read_text())
    cam = plate_camera.load(s["plate"])
    person = getattr(load_designs()[s["who"]], "height_cm", None) or 165
    h = plate_camera.figure_height(s["feet"][1], cam, plate_camera.pose_height_m(meta), person)
    depth = plate_camera.depth_map(s["plate"]) if not plate_camera.depth_path(s["plate"]).exists() else Image.open(plate_camera.depth_path(s["plate"]))
    depth = depth.convert("L").resize(Image.open(s["plate"]).size)
    front = plate_camera.in_front_mask(depth, (s["feet"][0], min(s["feet"][1], 0.999))) if s.get("front", True) else None
    d = OUT / name; d.mkdir(parents=True, exist_ok=True)
    board = insert.insert_many(s["plate"], [{"entry": entry, "feet": s["feet"], "height": h, "label": name, **({"in_front": front} if front else {}),
                                              "figure_only": True}], d / "board.png")
    # depth guide for the photo step: the plate's own depth, with the figure's visible pixels set just nearer than the
    # plate under its feet, so things in front of it (cut away above) stay in front
    patch = np.asarray(Image.open(d / "board.depth.png").convert("L"), dtype=np.int16)
    base = np.asarray(depth, dtype=np.int16)
    W, H = depth.size
    fx, fy = min(W - 1, round(s["feet"][0] * W)), min(H - 1, round(min(s["feet"][1], 1) * H) - 3)
    ref = int(np.median(base[max(0, fy - 4):fy + 1, max(0, fx - 4):fx + 5]))
    m = patch > 0
    rel = (patch - patch[m].mean()) * 0.25 if m.any() else 0
    if not s.get("front", True):  # nearest thing in the shot: just nearer than anything the figure covers
        ref = int(np.percentile(base, 99))
    out = np.where(m, np.clip(ref + 10 + rel, 0, 255), base).astype(np.uint8)
    Image.fromarray(out).save(d / "depth-guide.png")
    print(name, f"height {h:.2f} of frame", board, flush=True)


PHOTO_NEG = ("cartoon, anime, illustration, drawing, painting, 3d render, nude, nsfw, cleavage, text, logo, watermark, "
             "extra limbs, extra fingers, deformed, blurry, daylight, sunlight, two people, crowd")
UNION = "xinsir-union-sdxl-promax.safetensors"
DEPTH_CN, POSE_CN = (0.55, 0.65), (0.85, 0.75)  # (strength, end): depth keeps who is in front, pose sets the limbs


def photo_wf(plate, depth, pose, text, seed, denoise=0.75):
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "RealVisXL_V5.0_fp16.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": PHOTO_NEG, "clip": ["4", 1]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": plate}},
        "12": {"class_type": "ImageScale", "inputs": {"image": ["11", 0], "upscale_method": "lanczos", "width": 1216, "height": 832, "crop": "center"}},
        "13": {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}},
        "20": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": UNION}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_phototest/v5-photo", "images": ["8", 0]}},
    }
    pos, neg = ["6", 0], ["7", 0]
    for base, kind, img, (st, end) in ((30, "depth", depth, DEPTH_CN), (40, "openpose", pose, POSE_CN)):
        wf[str(base)] = {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["20", 0], "type": kind}}
        wf[str(base + 1)] = {"class_type": "LoadImage", "inputs": {"image": img}}
        wf[str(base + 2)] = {"class_type": "ImageScale", "inputs": {"image": [str(base + 1), 0], "upscale_method": "lanczos",
                             "width": 1216, "height": 832, "crop": "center"}}
        wf[str(base + 3)] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": pos, "negative": neg,
                             "control_net": [str(base), 0], "image": [str(base + 2), 0], "strength": st, "start_percent": 0.0,
                             "end_percent": end, "vae": ["4", 2]}}
        pos, neg = [str(base + 3), 0], [str(base + 3), 1]
    wf["3"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 30, "cfg": 5.0, "sampler_name": "dpmpp_2m", "scheduler": "karras",
               "denoise": denoise, "model": ["4", 0], "positive": pos, "negative": neg, "latent_image": ["13", 0]}}
    return wf


async def photos(name, seeds):
    from narrator.comfyui_backend import ComfyUIBackend
    s, d = SHOTS[name], OUT / name
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=900.0)
    up = [await be.upload_image(f"v5-{name}-{k}.png", b) for k, b in
          (("plate", s["plate"].read_bytes()), ("depth", (d / "depth-guide.png").read_bytes()), ("pose", (d / "board.pose.png").read_bytes()))]
    for seed in seeds:
        (d / f"photo-{seed}.png").write_bytes(await be.run_workflow(photo_wf(*up, s["photo"], seed)))
        print(name, "photo", seed, flush=True)


async def animes(name, photo_seed, seeds):
    import v1_whole_plate as v1
    from tools.shorts.plate_camera import depth_map
    s, d = SHOTS[name], OUT / name
    from narrator.comfyui_backend import ComfyUIBackend
    photo, depth = d / f"photo-{photo_seed}.png", d / f"photo-{photo_seed}.depth.png"
    if not depth.exists():
        depth_map(photo).save(depth)
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=900.0)
    pn = await be.upload_image(f"v5-{name}-photo-{photo_seed}.png", photo.read_bytes())
    dn = await be.upload_image(f"v5-{name}-pdepth-{photo_seed}.png", depth.read_bytes())
    for seed in seeds:
        out = d / f"anime-{photo_seed}-{seed}.png"
        out.write_bytes(await be.run_workflow(v1.anime_wf(s, pn, dn, seed, v1.ANIME_DENOISE)))
        print(name, "anime", photo_seed, seed, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "guides":
        for n in (sys.argv[2:] or SHOTS):
            guides(n)
    elif sys.argv[1] == "photo":
        for n in (sys.argv[2:] or SHOTS):
            asyncio.run(photos(n, [11, 22, 33]))
    elif sys.argv[1] == "anime":
        asyncio.run(animes(sys.argv[2], int(sys.argv[3]), [5, 6]))
