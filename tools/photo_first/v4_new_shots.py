"""Throwaway test v4: a batch of new shots. Masked photo (v3) -> people-count QA -> house medium dark anime pass (v2 recipe).
Run from the worktree: ../../../.venv/bin/python <this> photos [shot...] | anime <shot> <photo_file_name> [...]"""
import asyncio, io, sys
from pathlib import Path

sys.path.insert(0, ".")
from PIL import Image
from narrator.comfyui_backend import ComfyUIBackend
from narrator.designs import load_designs
import narrator.design_sheets as ds
from tools.scene_images import square_on_blur, face_box, paste_face

sys.path.insert(0, str(Path(__file__).parent))
from v1_whole_plate import comfy_free, URL, D
from v3_masked import wf as masked_wf, mask_png, people, STYLE
import v2_house_look as v2
import v3_masked as v3

OUT = Path(__file__).parent / "out"
P = lambda place, name: D / place / "plates" / f"{name}.png"
# shot: (plate, slug, state, mask, photo prompt, anime action tags)
SHOTS = {
    "goro-yakitori": (P("hanabira-cho", "yakitori-stand"), "goro-bessho", "offduty", (0.42, 0.22, 0.84, 1.0),
        "RAW photo, a burly grey-bearded man in his sixties with a grey buzz cut and yellow welding goggles pushed up on his forehead, "
        "a robotic metal right arm, wearing an oil-stained dark grey zip hoodie and worn black jeans, standing at the yakitori stall eating a "
        "skewer, side view, wet street, rain",
        "standing at food stall, eating yakitori skewer, side view, rain, wet street, mechanical arm"),
    "jun-doorway": (P("ikebe-low", "alley-doorway"), "jun-arakawa", "offduty", (0.36, 0.12, 0.78, 1.0),
        "RAW photo, a tall broad-shouldered man in his forties with slicked back black hair, a goatee and dark tan skin, a gold earpiece, "
        "wearing a black silk shirt open at the collar and a gold chain collar, slim charcoal trousers, leaning his back against the alley "
        "wall beside a glowing doorway, arms crossed, three-quarter view, looking down the alley",
        "leaning against wall, arms crossed, three-quarter view, looking away, alley, glowing doorway"),
    "kenji-underpass": (P("the-loop", "underpass-wide"), "kenji-moro", "work", (0.22, 0.42, 0.86, 1.0),
        "RAW photo, a muscular young man with a black undercut and tattooed bare arms, wearing a sleeveless blue racing vest and baggy black "
        "cargo pants, black fingerless gloves, crouching beside a parked black and blue sport motorcycle checking the rear wheel, side view",
        "crouching beside motorcycle, checking wheel, side view, underpass, tattooed arms"),
    "kaede-platform": (P("ring-line", "platform-edge"), "kaede-mori", "offduty", (0.0, 0.3, 0.42, 0.96),
        "RAW photo, a young woman with very long orange hair in a high ponytail, wearing an oversized white zip hoodie with pink cuffs, black "
        "leggings and white sneakers, sitting on the platform bench looking at her phone, legs crossed, side view",
        "sitting on bench, looking at phone, legs crossed, side view, station platform"),
    "wataru-gates": (P("ring-line", "ticket-gates"), "wataru-ono", "work", (0.42, 0.18, 0.86, 1.0),
        "RAW photo, a tired tall man in his fifties with swept back black hair greying at the temples and stubble, wearing a long dark "
        "navy-black coat over a pale blue-grey shirt, walking through the ticket gate, side view, one hand in his coat pocket",
        "walking through ticket gate, side view, hand in pocket, train station, long coat"),
    "hara-corridor": (P("danchi-block", "corridor"), "old-hara", "offduty", (0.06, 0.36, 0.5, 1.0),
        "RAW photo, a thin hunched bald old man with bushy white eyebrows and a monocle, wearing a worn brown knit cardigan over a grey collared "
        "shirt, sitting on a small folding stool outside his apartment door in the corridor, hands on his knees, side view",
        "sitting on small stool, hands on knees, side view, apartment corridor, old man"),
    "mitsu-offramp": (P("the-loop", "offramp-arcade"), "mitsu", "offduty", (0.3, 0.34, 0.72, 1.0),
        "RAW photo, a young woman with very long straight pink hair and blunt bangs, wearing an oversized pastel pink knit sweater, black leggings "
        "and white sneakers, walking away up the wet street holding a clear umbrella, seen from behind, rain",
        "walking away, from behind, holding clear umbrella, rain, wet street, neon"),
    "nagi-counter": (P("mama-satos-izakaya", "toward-far-end"), "nagi-sumida", "offduty", (0.42, 0.3, 0.92, 1.0),
        "RAW photo, a tall slender woman with black hair in a low bun and red lips, wearing a plain grey wool sweater with a white shirt collar, "
        "sitting alone on a stool at the wooden counter with a glass of beer, three-quarter view from behind",
        "sitting on stool at counter, glass of beer, from behind, three-quarter view, izakaya, alone"),
    "tadamori-rooftop": (P("tenjo-heights", "rooftop-city-view"), "hoshikawa-tadamori", "offduty", (0.3, 0.28, 0.64, 1.0),
        "RAW photo, a thin short old man with slicked back white hair and round red-tinted glasses, wearing a plain dark grey kimono with a black "
        "haori, hands tucked into his sleeves, standing at the rooftop railing looking out over the city, seen from behind",
        "standing at railing, from behind, hands in sleeves, looking at city, rooftop, kimono"),
    "daichi-alley": (P("ikebe-low", "alley-from-above"), "daichi-tanabe", "offduty", (0.3, 0.38, 0.76, 1.0),
        "RAW photo from above, a huge broad man with a black buzz cut and a robotic metal right arm, wearing an oversized black zip hoodie with "
        "sleeves pushed up and black track pants, walking down the narrow wet alley in the rain, high angle",
        "walking, from above, high angle, rain, narrow alley, mechanical arm"),
    "yuki-street": (P("hanabira-cho", "street-vanishing"), "yuki-shirasagi", "offduty", (0.12, 0.28, 0.52, 1.0),
        "RAW photo, a slender woman with a platinum blonde bob and blunt bangs, wearing a short white wool coat over a cream turtleneck, black "
        "tailored trousers and black boots, walking past the neon shop fronts, side view, looking at a shop window",
        "walking, side view, looking at shop window, neon street, wet pavement"),
    "akira-platform": (P("ring-line", "platform-wide"), "akira-sendo", "offduty", (0.55, 0.22, 0.86, 0.96),
        "RAW photo, a tall slender man with long messy silver hair in a low ponytail, wearing a plain dark grey wrap jacket over a black "
        "turtleneck and loose black trousers, leaning against a pillar with his arms crossed waiting for the train, side view",
        "leaning on pillar, arms crossed, side view, waiting, station platform, long silver hair"),
}


async def photos(shot, seeds=(11, 22, 33)):
    plate, _, _, box, text, _ = SHOTS[shot]
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=600.0)
    pn = await be.upload_image(f"pt4-plate-{shot}.png", plate.read_bytes())
    mn = await be.upload_image(f"pt4-mask-{shot}.png", mask_png(box))
    for s in seeds:
        out = OUT / f"{shot}-masked-{s}.png"
        out.write_bytes(await be.run_workflow(masked_wf(pn, mn, text + STYLE.replace("she is", "the only person"), s)))
        n = people(out)
        print(shot, s, f"people={n}", "REJECT" if n >= 2 else "OK", flush=True)


async def anime(shot, photo: Path, seeds=(5, 6), who=None, state=None, what=None):
    from tools.shorts.plate_camera import depth_map
    if shot in SHOTS:
        _, who, state, _, _, what = SHOTS[shot]
    d = load_designs()[who]
    st = D / who / "wardrobe" / state
    depth = photo.with_suffix(".depth.png")
    if not depth.exists():
        depth_map(photo).save(depth)
    be = ComfyUIBackend(base_url=URL, profile="noobai", timeout=900.0)
    ref = await be.upload_image(f"pt-ref-{who}-{state}.png", square_on_blur(ds.front_figure((st / "turnaround.png").read_bytes())))
    up = {}
    for k, f in (("photo", photo), ("depth", depth)):
        b = io.BytesIO(); Image.open(f).convert("RGB").resize(ds.SCENE_SIZE).save(b, "PNG")
        up[k] = await be.upload_image(f"pt4-{k}-{photo.stem}.png", b.getvalue())
    pos, neg = ds.scene_prompt(d, what)
    pos = ds._join(pos, d.wardrobe[state].tags)
    neg = ", ".join(t for t in (x.strip() for x in neg.split(",")) if t and t not in v2.CUT)
    neg += ", (cleavage, open clothes, exposed chest, bra, underwear, lingerie:1.4), extra person, extra legs, floating shoe"
    for s in seeds:
        wf = ds.natural_scene_workflow(f"{what}, detailed background, {pos}", neg, s, ref, up["photo"])
        wf["3"]["inputs"]["denoise"] = v2.DENOISE
        wf["80"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "noob_sdxl_controlnet_depth.safetensors"}}
        wf["81"] = {"class_type": "LoadImage", "inputs": {"image": up["depth"]}}
        wf["82"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": wf["3"]["inputs"]["positive"], "negative": wf["3"]["inputs"]["negative"],
                    "control_net": ["80", 0], "image": ["81", 0], "strength": v2.DEPTH_STRENGTH, "start_percent": 0.0, "end_percent": v2.DEPTH_END}}
        wf["3"]["inputs"].update(positive=["82", 0], negative=["82", 1])
        png = await be.run_workflow(wf)
        box = face_box(png)
        if box:
            crop = Image.open(io.BytesIO(png)).convert("RGB").crop(box).resize((1024, 1024), Image.LANCZOS)
            b = io.BytesIO(); crop.save(b, "PNG")
            fn = await be.upload_image(f"pt4-face-{shot}.png", b.getvalue())
            fp, fneg = ds.portrait_prompt(d, state)
            png = paste_face(png, await be.run_workflow(ds.face_workflow(ds._join(fp, ds.SCENE_MOOD), fneg, s, fn)), box)
        png = await hands_pass(be, png, d, state, s, shot)
        final = await be.run_workflow(ds.upscale_workflow(await be.upload_image(f"pt4-up-{shot}.png", png)))
        (OUT / f"{photo.stem}-house-{s}.png").write_bytes(ds.lift_blacks(final))
        print(shot, photo.name, "house", s, "face" if box else "no-face", flush=True)


HAND_DENOISE = 0.32  # light: fixes finger shapes, keeps what the hand is (chrome, glove, sleeve) and how it's lit


def hand_boxes(png: bytes, limit: int = 2) -> list[tuple[int, int, int, int]]:
    """Squares around the most confident hands, padded so the wrist and what it holds are repainted too."""
    from imgutils.detect import detect_hands
    im = Image.open(io.BytesIO(png)).convert("RGB")
    out = []
    for (x0, y0, x1, y1), _, score in sorted(detect_hands(im), key=lambda h: -h[2])[:limit]:
        if score < 0.4:
            continue
        side = min(max(96, int(max(x1 - x0, y1 - y0) * 1.8)), *im.size)
        left = max(0, min(im.width - side, (x0 + x1) // 2 - side // 2))
        top = max(0, min(im.height - side, (y0 + y1) // 2 - side // 2))
        out.append((left, top, left + side, top + side))
    return out


async def hands_pass(be, png: bytes, d, state: str, seed: int, shot: str) -> bytes:
    gloves = ", ".join(t.strip() for t in d.wardrobe[state].tags.split(",") if "glove" in t)
    pos = ds._join(ds.CHARACTER_QUALITY, "anime screenshot, cel shading, detailed hand, five fingers, natural hand pose", gloves, ds.SCENE_MOOD)
    neg = "extra fingers, missing fingers, fused fingers, deformed hand, six fingers, bad anatomy, photo, realistic, text"
    for i, box in enumerate(hand_boxes(png)):
        crop = Image.open(io.BytesIO(png)).convert("RGB").crop(box).resize((768, 768), Image.LANCZOS)
        b = io.BytesIO(); crop.save(b, "PNG")
        name = await be.upload_image(f"pt4-hand-{shot}-{i}.png", b.getvalue())
        wf = ds.face_workflow(pos, neg, seed + i, name)
        for node in wf.values():
            if node["class_type"] == "KSampler":
                node["inputs"]["denoise"] = HAND_DENOISE
        png = paste_face(png, await be.run_workflow(wf), box)
    return png


if __name__ == "__main__":
    try:
        if sys.argv[1] == "photos":
            for shot in (sys.argv[2:] or SHOTS):
                asyncio.run(photos(shot))
        else:
            a = sys.argv[2:]
            for shot, f in zip(a[::2], a[1::2]):
                if shot in SHOTS:
                    asyncio.run(anime(shot, OUT / f))
                else:  # one of the v3 cases
                    c = v2.CASES[shot]
                    asyncio.run(anime(shot, OUT / f, who=c["who"], state=c["state"], what=c["what"]))
    finally:
        comfy_free()
