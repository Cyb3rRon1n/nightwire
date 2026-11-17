"""Throwaway test v2: photo-first, finished with the approved medium dark scene recipe
(CFG 3.5 + refine, turnaround IPAdapter, face pass, upscale, lifted blacks), started from the photo with its depth as a guide.
Run from the worktree: ../../../.venv/bin/python <this> photos [case...] | anime <case> <photo_seed> [<case> <seed> ...]"""
import asyncio, io, sys, urllib.request
from pathlib import Path

sys.path.insert(0, ".")
from PIL import Image
from narrator.comfyui_backend import ComfyUIBackend
from narrator.designs import load_designs
import narrator.design_sheets as ds
from tools.scene_images import square_on_blur, face_box, paste_face

sys.path.insert(0, str(Path(__file__).parent))
from v1_whole_plate import photo_wf, comfy_free, URL, D

OUT = Path(__file__).parent / "out"
DEPTH_STRENGTH, DEPTH_END, DENOISE = 0.6, 0.6, 0.72
CASES = {
    "desk": dict(plate=D / "rins-room/plates/desk-screens.png", who="rin-kageyama", state="offduty",
                 photo="RAW photo, a young woman with a short black pixie haircut sitting in a desk chair at a desk with three glowing "
                       "computer monitors, seen from behind over her shoulder, hands on the keyboard, small warm desk lamp, "
                       "dark room at night, blue monitor glow on her, 35mm film, realistic, natural proportions",
                 what="sitting at a desk, from behind, over the shoulder, hands on keyboard, desk chair, glowing monitors, desk lamp"),
    "bed": dict(plate=D / "danchi-block/plates/flat-room.png", who="saeko-kirigaya", state="offduty",
                photo="RAW photo, a young woman with long straight black hair lying on her side on a futon on a tatami floor, head on "
                      "a pillow, eyes open, one hand resting by her face, under a blanket, small dark apartment at night, low camera "
                      "near the floor, dim light, 35mm film, realistic",
                what="lying on side, on futon, head on pillow, hand by face, under blanket, tatami, dark room"),
    "bar": dict(plate=D / "mama-satos-izakaya/plates/along-counter.png", who="saeko-kirigaya", state="work",
                photo="RAW photo, a young woman with long straight black hair in a dark jacket sitting on a wooden bar stool at an "
                      "izakaya counter, three-quarter side view, forearms on the counter, holding a small sake cup, warm paper lantern "
                      "light, night, 35mm film, realistic, natural proportions",
                what="sitting on bar stool, at wooden counter, forearms on counter, holding sake cup, from side, paper lanterns, izakaya"),
    "window": dict(plate=D / "rins-room/plates/bed-window.png", who="rin-kageyama", state="offduty",
                   photo="RAW photo, a young woman with a short black pixie haircut sitting on the edge of an unmade bed hugging her knees, "
                         "seen from behind three-quarter, looking out of a large window at city neon lights at night, pink and cyan light "
                         "on her, small dark bedroom, 35mm film, realistic, natural proportions",
                   what="sitting on bed, hugging knees, from behind, looking out window, city lights, neon light on her, bedroom"),
    "rail": dict(plate=D / "tenjo-heights/plates/rooftop-rail.png", who="saeko-kirigaya", state="work",
                 photo="RAW photo, a young woman with long straight black hair in a dark jacket leaning her forearms on a metal rooftop "
                       "railing, side view, looking out over a vast city of lights far below at night, wind in her hair, 35mm film, "
                       "realistic, natural proportions",
                 what="leaning on railing, forearms on railing, side view, looking at city, rooftop, night city lights below, wind"),
    "train": dict(plate=D / "ring-line/plates/carriage-interior.png", who="rin-kageyama", state="offduty",
                  photo="RAW photo, a young woman with a short black pixie haircut sitting alone on the long bench seat of an empty "
                        "commuter train at night, side view, head leaning against the window, hands in her lap, fluorescent light, "
                        "35mm film, realistic, natural proportions",
                  what="sitting on train bench, side view, head leaning on window, hands in lap, empty train carriage, fluorescent light"),
}
CUT = {"science fiction", "machinery", "control room", "computer", "monitor", "cable"}  # the scene negative fights rooms with screens


async def photos(case, seeds):
    c = CASES[case]
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=600.0)
    name = await be.upload_image(f"pt-plate-{case}.png", c["plate"].read_bytes())
    for s in seeds:
        out = OUT / f"{case}-photo-{s}.png"
        if not out.exists():
            out.write_bytes(await be.run_workflow(photo_wf(name, c["photo"], s)))
        print(case, "photo", s, flush=True)


async def anime(case, ps, seeds):
    from tools.shorts.plate_camera import depth_map
    c = CASES[case]
    d = load_designs()[c["who"]]
    st = D / c["who"] / "wardrobe" / c["state"]
    photo = OUT / f"{case}-photo-{ps}.png"
    depth = OUT / f"{case}-photo-{ps}.depth.png"
    if not depth.exists():
        depth_map(photo).save(depth)
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=900.0)
    ref = await be.upload_image(f"pt-ref-{c['who']}-{c['state']}.png", square_on_blur(ds.front_figure((st / "turnaround.png").read_bytes())))
    buf = io.BytesIO(); Image.open(photo).convert("RGB").resize(ds.SCENE_SIZE).save(buf, "PNG")
    pn = await be.upload_image(f"pt2-photo-{case}-{ps}.png", buf.getvalue())
    buf = io.BytesIO(); Image.open(depth).convert("RGB").resize(ds.SCENE_SIZE).save(buf, "PNG")
    dn = await be.upload_image(f"pt2-depth-{case}-{ps}.png", buf.getvalue())
    pos, neg = ds.scene_prompt(d, c["what"])
    pos = ds._join(pos, d.wardrobe[c["state"]].tags)
    neg = ", ".join(t for t in (x.strip() for x in neg.split(",")) if t and t not in CUT)
    for s in seeds:
        wf = ds.natural_scene_workflow(f"{c['what']}, detailed background, {pos}", neg, s, ref, pn)
        wf["3"]["inputs"]["denoise"] = DENOISE
        wf["80"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "noob_sdxl_controlnet_depth.safetensors"}}
        wf["81"] = {"class_type": "LoadImage", "inputs": {"image": dn}}
        wf["82"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": wf["3"]["inputs"]["positive"], "negative": wf["3"]["inputs"]["negative"],
                    "control_net": ["80", 0], "image": ["81", 0], "strength": DEPTH_STRENGTH, "start_percent": 0.0, "end_percent": DEPTH_END}}
        wf["3"]["inputs"].update(positive=["82", 0], negative=["82", 1])
        png = await be.run_workflow(wf)
        box = face_box(png)
        if box:
            crop = Image.open(io.BytesIO(png)).convert("RGB").crop(box).resize((1024, 1024), Image.LANCZOS)
            b = io.BytesIO(); crop.save(b, "PNG")
            fn = await be.upload_image(f"pt2-face-{case}.png", b.getvalue())
            fp, fneg = ds.portrait_prompt(d, c["state"])
            png = paste_face(png, await be.run_workflow(ds.face_workflow(ds._join(fp, ds.SCENE_MOOD), fneg, s, fn)), box)
        up = await be.run_workflow(ds.upscale_workflow(await be.upload_image(f"pt2-up-{case}.png", png)))
        (OUT / f"{case}-house-{ps}-{s}.png").write_bytes(ds.lift_blacks(up))
        print(case, "house", ps, s, "face" if box else "no-face", flush=True)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "photos":
            for case in (sys.argv[2:] or CASES):
                asyncio.run(photos(case, [11, 22, 33]))
        else:
            a = sys.argv[2:]
            for case, ps in zip(a[::2], a[1::2]):
                asyncio.run(anime(case, int(ps), [5, 6]))
    finally:
        comfy_free()
