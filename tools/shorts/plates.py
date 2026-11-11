"""Location plates: the empty room from each camera direction a short needs. A plate is approved once (review id
plate--<place>--<name>) and reused by every later short at that place. Catalogues live in narrator/worlds/plates/,
outside the designs folder, because every design tool globs designs/*.toml as a design."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

GUIDE_STRENGTH = 0.8  # lineart ControlNet: strong enough that each direction shows its own wall
GUIDE_END = 0.85
PLATES_ROOT = Path(__file__).resolve().parents[2] / "narrator" / "worlds" / "plates"


def default_root() -> Path:
    """One plates root for sheet, submit, preflight and the review inbox; resolved at call time."""
    env = os.environ.get("NIGHTWIRE_PLATES_DIR")
    return Path(env) if env else PLATES_ROOT


@dataclass
class Plate:
    name: str
    view: str
    source: str = ""   # an existing approved image of the place adopted as this plate
    tags: str = ""     # replaces the place tags for this direction (they would pull in the wrong wall)
    avoid: list[str] = field(default_factory=list)  # extra negative terms for this direction
    mood: str = ""     # replaces the scene's time/weather/light line (an exterior plate of a mostly-indoor scene)


def load_plates(place: str, plates_root: Path | None = None) -> dict[str, Plate]:
    path = (plates_root or default_root()) / f"{place}.toml"
    if not path.exists():
        return {}
    return {p["name"]: Plate(**p) for p in tomllib.loads(path.read_text()).get("plate", [])}


def plate_path(design_dir: Path, place: str, plate: Plate) -> Path:
    return design_dir / place / (plate.source or f"plates/{plate.name}.png")


def plate_id(place: str, name: str, path: Path | None = None) -> str:
    """Review id of a plate; once the chosen file exists it carries the file's hash."""
    from tools.shorts.approve import file_sha
    base = f"plate--{place}--{name}"
    return f"{base}--{file_sha(path)}" if path is not None and path.exists() else base


NO_TEXT = "text, english text, latin letters, signature, watermark"


def plate_workflow(place, look: str, not_visible, plate: Plate, lineart_name: str | None, seed: int, mood: str = "") -> dict:
    """look = model.scene_look(short); not_visible = the bible's list, which becomes the negative.
    A plate with its own tags uses them instead of the place tags, and mood (model.scene_mood) instead of look."""
    from tools.imagegen import build
    tags = plate.tags or place.alt_tags or place.tags
    if plate.tags:
        look = plate.mood or mood
    # "empty room" turned the outdoor block facade into alleys and hallways (2026-11-10, 8 candidates).
    empty = "no humans" if "outdoors" in tags else "empty room, no humans"
    from narrator.design_sheets import _LOCATION_MOOD, _LOCATION_NEGATIVE, sheet_workflow
    text = build(f"({plate.view}:1.3), {empty}, {look}, {tags}, {_LOCATION_MOOD}", "scene", False,
                 ", ".join(["people, person, 1girl, 1boy", *not_visible, *plate.avoid, NO_TEXT, _LOCATION_NEGATIVE]), "base", seed)
    # The approved location look (2026-11-03 "medium dark"): CFG 3.5 plus the 2x refine pass. A single first pass at CFG 4.5
    # read as photographic next to the sheets (owner, 2026-11-11). Output 1824x1248, no final 2x upscale.
    wf = sheet_workflow(text["6"]["inputs"]["text"], text["7"]["inputs"]["text"], seed, size=(1216, 832), cfg=3.5)
    wf["9"]["inputs"]["images"] = ["35", 0]
    del wf["40"]
    if lineart_name:
        wf["60"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "noob-sdxl-controlnet-lineart_anime.fp16.safetensors"}}
        wf["61"] = {"class_type": "LoadImage", "inputs": {"image": lineart_name}}
        wf["62"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": wf["3"]["inputs"]["positive"],
                    "negative": wf["3"]["inputs"]["negative"], "control_net": ["60", 0], "image": ["61", 0],
                    "strength": GUIDE_STRENGTH, "start_percent": 0.0, "end_percent": GUIDE_END}}
        wf["3"]["inputs"].update(positive=["62", 0], negative=["62", 1])
        if "34" in wf:  # high-res second pass (not in the "base" size, handled in case that changes)
            wf["34"]["inputs"].update(positive=["62", 0], negative=["62", 1])
    wf["9"]["inputs"]["filename_prefix"] = f"nightwire_plates/{plate.name}"
    return wf


def candidate_path(design_dir: Path, place: str, name: str, n: int) -> Path:
    return design_dir / place / "plates" / f"{name}-c{n:02d}.png"


def plan_jobs(short, work: Path, design_dir: Path, plates_root: Path | None = None, seeds: int = 3, redo: bool = False):
    """[(out_path, plate, lineart_path_or_None, n)] for each plate a shot names that has no chosen file.
    Existing candidates are kept unless redo. Uses the lineart of the first shot (shot order) that names the plate."""
    catalogue = load_plates(short.place, plates_root)
    jobs, seen = [], set()
    for shot in short.shots:
        plate = catalogue.get(shot.plate)
        if plate is None or plate.name in seen:
            continue
        seen.add(plate.name)
        if plate.source or plate_path(design_dir, short.place, plate).exists():
            continue
        art = work / "shots" / shot.id / "guide" / "start-room-lineart.png"
        for n in range(1, seeds + 1):
            out = candidate_path(design_dir, short.place, plate.name, n)
            if redo or not out.exists():
                jobs.append((out, plate, art if art.exists() else None, n))
    return jobs


def choose(design_dir: Path, place: str, plate: Plate, n: int) -> Path:
    import shutil
    if plate.source:
        raise ValueError(f"plate {plate.name} is an adopted image ({plate.source}); it is not overwritten")
    src = candidate_path(design_dir, place, plate.name, n)
    if not src.exists():
        raise ValueError(f"no candidate {src.name}")
    dst = plate_path(design_dir, place, plate)
    shutil.copyfile(src, dst)
    return dst


async def render(jobs, backend, designs_place, look: str, not_visible, seed: int, mood: str = "") -> list[str]:
    """jobs from plan_jobs. One failure does not stop the rest."""
    errors = []
    for out, plate, art, n in jobs:
        try:
            name = await backend.upload_image(f"plate-guide-{plate.name}.png", art.read_bytes()) if art else None
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(await backend.run_workflow(plate_workflow(designs_place, look, not_visible, plate, name, seed + n - 1, mood)))
            print(out, flush=True)
        except Exception as e:  # noqa: BLE001 - keep the batch going
            errors.append(f"{out.name}: {e}")
    return errors


def run(jobs, url: str, designs_place, look: str, not_visible, seed: int, mood: str = "") -> list[str]:
    if not jobs:
        return []
    import asyncio

    from narrator.comfyui_backend import ComfyUIBackend
    from tools.design_studio import _gpu_etiquette
    _gpu_etiquette(url, before=True)
    try:
        return asyncio.run(render(jobs, ComfyUIBackend(base_url=url, profile="noobai", timeout=600.0), designs_place, look, not_visible, seed, mood))
    finally:
        _gpu_etiquette(url, before=False)  # frees VRAM for the narrator
