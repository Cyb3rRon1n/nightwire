"""Start/end keyframe candidates per shot: the house NoobAI model, guided by grey-box depth + OpenPose (chained ControlNets) and
one prompt per character limited to that character's screen region. Mirrors plates.py (plan_jobs / render / run / choose)."""

import shutil
import sys
from pathlib import Path

from PIL import Image

W, H = 1216, 832


def needed(shot) -> list[str]:
    """The keyframes a shot needs: start for i2v; end when end_frame or the set of characters changes."""
    out = ["start"] if shot.mode == "i2v" else []
    if shot.mode == "i2v" and (shot.end_frame or set(shot.at_start) != set(shot.at_end)):
        out.append("end")
    return out


def chosen_path(work: Path, shot_id: str, which: str) -> Path:
    return work / "shots" / shot_id / f"keyframe-{which}.png"


def candidate_path(work: Path, shot_id: str, which: str, n: int) -> Path:
    return work / "shots" / shot_id / "keyframes" / f"{which}-c{n:02d}.png"


REGION_STRENGTH = 1.5
DEPTH_NET, DEPTH_STRENGTH, DEPTH_END = "noob_sdxl_controlnet_depth.safetensors", 0.6, 0.6
POSE_NET, POSE_STRENGTH, POSE_END = "noob_openpose_pre.safetensors", 0.9, 0.8
WARDROBE_WEIGHT = 1.4
SIZE_EXTRA = {"MCU": "upper body", "CU": "close-up", "ECU": "close-up", "WS": "full body, wide shot", "EWS": "full body, wide shot"}
BEHIND = ("back of head", "from behind", "face not visible")


def _weight(text: str, w: float) -> str:
    """A ComfyUI weight group; parens and colons in the text would break the weighting syntax."""
    text = " ".join(text.translate({ord(c): " " for c in "():"}).split())
    return f"({text}:{w})" if text else ""


def keyframe_workflow(short, shot, designs, which, regions, depth_name, pose_name, seed, plate=None, back=()) -> dict:
    """back: figure ids the pose json says are seen from behind."""
    from tools.design_scenes import _crowd, _region_tags
    from tools.image_studio import _subject
    from tools.imagegen import MATURE_18, MATURE_18_MALE, MATURE_18_OTHER, build
    from tools.shorts.model import scene_look, scene_mood
    from tools.shorts.plates import NO_TEXT
    from tools.shorts.stills import SIZE_WORDS
    place = designs[short.place]
    boxes = regions.get(which, {})
    who = sorted((c for c in boxes if c in short.cast), key=lambda c: boxes[c][0])
    if len(who) > 2:  # two characters at most, like stills: keep the leftmost two
        print(f"note: {shot.id} {which}: more than two characters in frame; dropping {', '.join(who[2:])}", file=sys.stderr)
        who = who[:2]
    kw = {}
    if len(who) == 1:
        kw["subject"] = _subject(designs[short.cast[who[0]]])
    elif len(who) >= 2:  # the crowd text is the subject so nothing is prepended twice
        kw["subject"] = _crowd(designs[short.cast[who[0]]], designs[short.cast[who[1]]])
    tags, look = (plate.tags, scene_mood(short)) if plate and plate.tags else (place.alt_tags or place.tags, scene_look(short))  # as plate_workflow
    terms = [t.strip() for x in (SIZE_WORDS.get(shot.size, ""), SIZE_EXTRA.get(shot.size, ""), shot.angle) for t in x.split(",")]
    lead = _weight(", ".join(dict.fromkeys(t for t in terms if t)).replace(",", " ,"), 1.4).replace(" ,", ",")
    words = ", ".join(x for x in (lead, "solo" if len(who) == 1 else "", tags, look) if x)
    negative = ", ".join(x for x in ["merged bodies, fused faces, extra arms", *(short.scene.not_visible if short.scene else []),
                          _weight(", ".join(short.avoid), WARDROBE_WEIGHT), *(plate.avoid if plate else []), NO_TEXT] if x)
    wf = build(words, "subject" if who else "scene", False, negative, "base", seed, **kw)
    wf["5"]["inputs"].update(width=W, height=H)
    clip, combined = wf["6"]["inputs"]["clip"], ["6", 0]
    for i, cid in enumerate(who):
        d = designs[short.cast[cid]]
        x0, y0, x1, y1 = boxes[cid]
        adult = {"1girl": MATURE_18, "1boy": MATURE_18_MALE}.get(_subject(d), MATURE_18_OTHER)
        pose = (shot.at_start if which == "start" else shot.at_end).get(cid, "")
        behind = _weight("from behind, back of head", 1.4) if cid in back or any(b in shot.frame.get(cid, "").lower() for b in BEHIND) else ""
        text = ", ".join(x for x in (_subject(d), adult, _weight(pose, 1.3), behind, _region_tags(d), short.locks.get(cid, ""), _weight(short.wardrobe.get(cid, ""), WARDROBE_WEIGHT),
                                      shot.props.get(cid, "")) if x)
        n = 70 + i * 3
        wf[str(n)] = {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": clip}}
        bw, bh = max(64, int((x1 - x0) * W) // 8 * 8), max(64, int((y1 - y0) * H) // 8 * 8)
        bx, by = min(int(x0 * W) // 8 * 8, W - bw), min(int(y0 * H) // 8 * 8, H - bh)
        wf[str(n + 1)] = {"class_type": "ConditioningSetArea", "inputs": {
            "conditioning": [str(n), 0], "width": bw, "height": bh, "x": bx, "y": by, "strength": REGION_STRENGTH}}
        wf[str(n + 2)] = {"class_type": "ConditioningCombine", "inputs": {"conditioning_1": combined, "conditioning_2": [str(n + 1), 0]}}
        combined = [str(n + 2), 0]
    neg_in = wf["3"]["inputs"]["negative"]
    for base, net, img, strength, end in ((60, DEPTH_NET, depth_name, DEPTH_STRENGTH, DEPTH_END), (63, POSE_NET, pose_name, POSE_STRENGTH, POSE_END)):
        wf[str(base)] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": net}}
        wf[str(base + 1)] = {"class_type": "LoadImage", "inputs": {"image": img}}
        wf[str(base + 2)] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": combined, "negative": neg_in, "control_net": [str(base), 0], "image": [str(base + 1), 0],
            "strength": strength, "start_percent": 0.0, "end_percent": end}}
        wf["3"]["inputs"].update(positive=[str(base + 2), 0], negative=[str(base + 2), 1])  # chained: pose takes depth's output
        combined, neg_in = [str(base + 2), 0], [str(base + 2), 1]
    if "34" in wf:  # high-res second pass (not in the "base" size, handled in case that changes)
        wf["34"]["inputs"].update(positive=["65", 0], negative=["65", 1])
    wf["9"]["inputs"]["filename_prefix"] = f"nightwire_shorts/{short.slug}-{shot.id}-{which}"
    return wf


def plan_jobs(short, work: Path, shot_id: str | None = None, which: str = "both", seeds: int = 4, redo: bool = False):
    """[(out_path, shot, which, guide_dir, regions, n)] for each needed keyframe with no chosen file.
    Shots without depth/pose guides or regions are skipped and named in the second return value."""
    from tools.shorts.guides import regions as load_regions
    jobs, skipped = [], []
    for shot in short.shots:
        if shot_id and shot.id != shot_id:
            continue
        shot_dir = work / "shots" / shot.id
        for w in needed(shot):
            if which != "both" and w != which:
                continue
            art = shot_dir / "guide"
            if not all((art / f"{w}-{k}.png").exists() for k in ("depth", "pose")):
                skipped.append(f"{shot.id} {w}: no depth/pose guide (run guides first)")
                continue
            if chosen_path(work, shot.id, w).exists():
                continue
            reg = load_regions(shot_dir)
            if not any(c in short.cast for c in reg.get(w, {})):
                skipped.append(f"{shot.id} {w}: no character regions in guide/regions.json (rerun guides)")
                continue
            for n in range(1, seeds + 1):
                out = candidate_path(work, shot.id, w, n)
                if redo or not out.exists():
                    jobs.append((out, shot, w, art, reg, n))
    return jobs, skipped


def choose(work: Path, shot_id: str, which: str, n: int) -> Path:
    if which not in ("start", "end"):
        raise ValueError(f"which must be start or end, not {which!r}")
    src = candidate_path(work, shot_id, which, n)
    if not src.exists():
        raise ValueError(f"no candidate {src.name}")
    with Image.open(src) as im:
        if im.size != (W, H):
            raise ValueError(f"{src.name} is {im.size[0]}x{im.size[1]}; a keyframe must be {W}x{H}")
    dst = chosen_path(work, shot_id, which)
    shutil.copyfile(src, dst)
    return dst


async def render(jobs, backend, short, designs, seed: int) -> list[str]:
    """jobs from plan_jobs. One failure does not stop the rest."""
    from tools.shorts.guides import pose_json
    from tools.shorts.plates import load_plates
    errors, catalogue = [], load_plates(short.place)
    for out, shot, which, art, reg, n in jobs:
        try:
            names = [await backend.upload_image(f"key-{k}-{short.slug}-{shot.id}-{which}.png", (art / f"{which}-{k}.png").read_bytes()) for k in ("depth", "pose")]
            back = {f for f, v in pose_json(art.parent, which).items() if v.get("back")}
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(await backend.run_workflow(keyframe_workflow(short, shot, designs, which, reg, *names, seed + n - 1, catalogue.get(shot.plate), back)))
            print(out, flush=True)
        except Exception as e:  # noqa: BLE001 - keep the batch going
            errors.append(f"{out.name}: {e}")
    return errors


def run(jobs, url: str, short, designs, seed: int) -> list[str]:
    if not jobs:
        return []
    import asyncio

    from narrator.comfyui_backend import ComfyUIBackend
    from tools.design_studio import _gpu_etiquette
    _gpu_etiquette(url, before=True)
    try:
        return asyncio.run(render(jobs, ComfyUIBackend(base_url=url, profile="noobai", timeout=600.0), short, designs, seed))
    finally:
        _gpu_etiquette(url, before=False)  # frees VRAM for the narrator
