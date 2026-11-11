"""Blender stages the owner opens and edits: shots/<id>/stage.blend per shot, built headless on this PC.

    python -m tools.shorts stage <short> [shot]

Needs the plate's camera file (python -m tools.shorts camera <short>). The Nightwire add-on is installed into the local
Blender once; its Export buttons write board-<which>.owner.png, which `shorts boards` uses instead of its own board."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.greybox_library import build as lib_build
from tools.greybox_library import presets
from tools.shorts import plate_camera
from tools.shorts import plates as plate_mod

HERE = Path(__file__).parent / "greybox"
SCRIPT, ADDON, HELPERS = HERE / "blender_stage.py", HERE / "nightwire_stage_addon.py", HERE / "blender_build.py"
BLENDER = Path(os.environ.get("NIGHTWIRE_LOCAL_BLENDER", Path.home() / "opt" / "blender" / "blender"))


def job(short, shot, design_dir: Path, work: Path, heights_cm: dict, plates_root: Path | None = None) -> dict:
    catalogue = plate_mod.load_plates(short.place, plates_root)
    if shot.plate not in catalogue:
        raise ValueError(f"{shot.id}: no plate named {shot.plate!r} for {short.place}")
    plate = plate_mod.plate_path(design_dir, short.place, catalogue[shot.plate])
    cam = plate_camera.load(plate) if plate.exists() else None
    if cam is None:
        raise ValueError(f"{shot.id}: plate {shot.plate!r} has no camera yet (python -m tools.shorts camera {short.slug})")
    from PIL import Image
    figures = []
    for b in (b for b in shot.boards if b.which == "start"):
        cm = heights_cm.get(b.figure) or presets.REF_HEIGHT_CM
        rig = lib_build.jobs([b.pose], [b.camera], cm, Path("."))[0]["rig"]
        figures.append({"label": b.figure, "feet": list(b.feet), "yaw": presets.CAMERAS[b.camera]["yaw"], "rig": rig})
    return {"title": f"{short.title} {shot.id}", "plate": str(plate.resolve()), "res": list(Image.open(plate).size),
            "lens": shot.lens or 35.0, "horizon_y": cam["horizon_y"], "cam_height_m": cam["cam_height_m"],
            "figures": figures, "shot_dir": str((work / "shots" / shot.id).resolve()), "helpers": str(HELPERS.resolve())}


def install_addon(blender: Path = BLENDER) -> None:
    """Copies the add-on into Blender's user add-ons and enables it in the saved preferences (idempotent)."""
    version = subprocess.run([str(blender), "--version"], capture_output=True, text=True, check=True).stdout.split()[1]
    dest = Path.home() / ".config" / "blender" / ".".join(version.split(".")[:2]) / "scripts" / "addons"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(ADDON, dest / "nightwire_stage.py")
    subprocess.run([str(blender), "-b", "--python-expr",
                    "import bpy; bpy.ops.preferences.addon_enable(module='nightwire_stage'); bpy.ops.wm.save_userpref()"],
                   capture_output=True, check=True)


def build(short, design_dir: Path, work: Path, heights_cm: dict, shot: str | None = None, blender: Path = BLENDER) -> list[Path]:
    out = []
    for sh in short.shots:
        if (shot and sh.id != shot) or not sh.boards:
            continue
        j = job(short, sh, design_dir, work, heights_cm)
        dest = Path(j["shot_dir"]) / "stage.blend"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            jp = Path(tmp) / "job.json"
            jp.write_text(json.dumps(j))
            r = subprocess.run([str(blender), "-b", "-P", str(SCRIPT), "--", str(jp), str(dest)], capture_output=True, text=True)
        if r.returncode != 0 or not dest.exists():
            raise RuntimeError(f"{sh.id}: Blender failed:\n" + (r.stdout + r.stderr)[-1500:])
        out.append(dest)
    return out
